"""Documents importants : papiers d'identité, fiches de paie, diplômes, impôts, logement…

Parmi tous les fichiers récupérés, repère ceux qui ont l'air de compter, d'après les mots de leur
nom ET de leurs dossiers : « CNI Jean.jpg », « Papiers/Impôts/2012/avis.pdf », « Bulletin de
salaire mars 2015.pdf ». Accents, majuscules, tirets et soulignés sont ignorés.

C'est volontairement large : il y aura des faux positifs (mieux vaut un document de trop qu'un
document important oublié). Les vidéos et la musique ne sont jamais retenues. Un document scanné
sous un nom sans rapport (« Scan0001.pdf ») ne peut pas être reconnu, sauf par son dossier.

Pour ajouter un mot : le placer dans la bonne catégorie ci-dessous (expression régulière, sur un
texte sans accents, en minuscules, où les mots sont séparés par une espace).
"""
from __future__ import annotations

import re
import unicodedata

# (clé, libellé, icône, motifs). La première catégorie qui correspond l'emporte.
CATEGORIES = [
    ("identite", "Identité et état civil", "🪪", [
        r"cartes? (nationale )?d ?identite", r"cni", r"passe ?ports?", r"passport", r"permis( de conduire)?",
        r"livrets? de famille", r"actes? d(e |u )?(naissance|mariage|deces|etat civil)",
        r"extraits? (d acte|de naissance|de mariage)", r"etat civil", r"titres? de sejour", r"cartes? de sejour",
        r"naturalisation", r"nationalite", r"cartes? vitale", r"identity card", r"id card",
        r"birth certificate", r"carte d electeur", r"pieces? d identite",
    ]),
    ("travail", "Travail, salaires et retraite", "💼", [
        r"fiches? de pa[iy]e", r"bulletins? de (pa[iy]e|salaires?)", r"pa[iy]e", r"salaires?", r"pay ?slips?",
        r"payroll", r"contrats? de travail", r"cdi", r"cdd", r"attestations? (employeur|de travail|pole emploi)",
        r"certificats? de travail", r"solde de tout compte", r"pole emploi", r"france travail", r"assedic",
        r"chomage", r"retraites?", r"carsat", r"agirc", r"arrco", r"releves? de carriere", r"cnav", r"urssaf",
        r"msa", r"licenciement", r"demission", r"rupture conventionnelle", r"cv", r"curriculum",
        r"avenants?", r"interessement", r"participation salariale",
    ]),
    ("diplomes", "Diplômes et scolarité", "🎓", [
        r"diplomes?", r"diplomas?", r"baccalaureat", r"bac", r"brevets?", r"bts", r"dut", r"bep",
        r"licences? (de|d|en|pro|professionnelle)", r"masters? (1|2|de|d|en|pro)", r"doctorat",
        r"releves? de notes", r"bulletins? (scolaires?|trimestriels?|de notes)", r"attestations? de reussite",
        r"certificats? de scolarite", r"carnets? de notes", r"livret scolaire", r"delf", r"toeic", r"toefl",
        r"transcripts?", r"attestations? de formation",
    ]),
    ("impots", "Impôts", "🧾", [
        r"impots?", r"imposition", r"non imposition", r"declarations? (de|des) revenus", r"declarations? d impots?",
        r"2042", r"taxe fonciere", r"taxes? d habitation", r"dgfip", r"tax returns?", r"fisc(al|aux|alite)?",
        r"prelevement a la source",
    ]),
    ("sante", "Santé", "🩺", [
        r"ordonnances?", r"comptes? rendus?", r"analyses? (de sang|medicales?|biologiques?)",
        r"resultats? d analyses?", r"radiographies?", r"irm", r"echographies?",
        r"mutuelles?", r"carnets? de (sante|vaccinations?)", r"vaccins?", r"vaccinations?",
        r"certificats? medica(l|ux)", r"cpam", r"ameli", r"securite sociale", r"hopita(l|ux)", r"medecins?",
        r"arrets? (de )?travail", r"invalidite", r"mdph", r"medica(l|les?|ux)", r"sante",
    ]),
    ("vehicule", "Véhicules", "🚗", [
        r"cartes? grises?", r"certificats? d immatriculation", r"controles? techniques?", r"contraventions?",
        r"amendes?", r"assurances? (auto|voiture|moto)", r"certificat de cession",
    ]),
    ("logement", "Logement et propriété", "🏠", [
        r"bail", r"baux", r"contrats? de location", r"quittances?( de loyer)?", r"etats? des lieux",
        r"actes? de vente", r"actes? notaries?", r"compromis( de vente)?", r"titres? de propriete",
        r"offres? de pret", r"prets? immobiliers?", r"tableaux? d amortissement", r"syndic", r"copropriete",
        r"cadastre", r"permis de construire", r"assurances? habitation", r"loyers?", r"diagnostics? immobiliers?",
    ]),
    ("banque", "Banque, assurances et crédits", "🏦", [
        r"rib", r"iban", r"releves? (de comptes?|bancaires?|de banque)", r"banques?", r"credits? (immobiliers?|conso|auto)",
        r"contrats? de credit", r"emprunts?", r"assurances?", r"contrats? d assurance", r"attestations? d assurance",
        r"sinistres?", r"assurance vie", r"placements?", r"livret a", r"pea", r"epargne", r"prevoyance",
        r"bank statements?", r"insurance",
    ]),
    ("famille", "Famille, justice et succession", "⚖️", [
        r"testaments?", r"successions?", r"heritages?", r"donations?", r"jugements?", r"divorces?",
        r"contrats? de mariage", r"pacs", r"tribunal", r"procurations?", r"tutelle", r"curatelle", r"avocats?",
        r"huissiers?", r"notaires?", r"obseques", r"funera(ire|illes)", r"adoption", r"caf",
        r"allocations? familiales?",
    ]),
    ("factures", "Factures et garanties", "🧾", [
        r"factures?", r"invoices?", r"garanties?", r"bons? de garantie", r"devis", r"bons? de commande",
    ]),
    ("papiers", "Autres papiers", "📁", [
        r"papiers?", r"paperasses?", r"administrati(f|fs|ve|ves|on)", r"documents? importants?",
        r"dossiers? importants?", r"attestations?", r"certificats?", r"contrats?", r"cerfa", r"courriers? officiels?",
        r"justificatifs?", r"important",
    ]),
]
LABELS = {k: label for k, label, _, _ in CATEGORIES}
ICONS = {k: icon for k, _, icon, _ in CATEGORIES}

# Familles de fichiers (bilan.family) où chercher : pas les vidéos, la musique ni les fichiers techniques.
FAMILIES = {"Textes", "Tableurs", "Présentations", "PDF", "photo", "mail", "other"}

_RULES = [(k, re.compile(r"(?<![a-z0-9])(?:" + "|".join(p) + r")(?![a-z0-9])")) for k, _, _, p in CATEGORIES]
_NOT_WORD = re.compile(r"[^a-z0-9]+")
_EXT = re.compile(r"\.[a-z0-9]{1,5}$")


def normalize(text: str) -> str:
    """« Fiche_de_Paye-Février 2015.PDF » -> « fiche de paye fevrier 2015 »."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _NOT_WORD.sub(" ", _EXT.sub("", text)).strip()


def category(path: str, family: str | None = None):
    """Catégorie (clé) d'un fichier d'après son nom puis ses dossiers, ou None.
    path : chemin relatif (séparateur /) ; family : famille du fichier (bilan.family), si connue."""
    if family is not None and family not in FAMILIES:
        return None
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None
    name = normalize(parts[-1])
    for key, rx in _RULES:   # d'abord le nom du fichier, qui est le plus parlant
        if rx.search(name):
            return key
    folders = normalize(" / ".join(parts[:-1]))
    for key, rx in _RULES:
        if rx.search(folders):
            return key
    return None
