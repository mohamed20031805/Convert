import pdfplumber
from exporter import exporter_excel
from formats import morgan, triton

# ── Liste des formats disponibles ──
FORMATS = [triton, morgan]  # ordre important : triton d'abord (plus spécifique)

# ── Templates JSON par format ──
TEMPLATES = {
    "morgan": "templates/morgan_stanley.json",
    "triton": "templates/triton.json",
}

def detecter_format(chemin_pdf):
    with pdfplumber.open(chemin_pdf) as pdf:
        texte = pdf.pages[0].extract_text() or ""
    for fmt in FORMATS:
        if fmt.detecter(texte):
            return fmt
    return None

def traiter_pdf(chemin_pdf):
    print(f"\n🚀 Traitement : {chemin_pdf}")
    
    fmt = detecter_format(chemin_pdf)
    if not fmt:
        print("❌ Format non reconnu !")
        return
    
    print(f"📄 Format détecté : {fmt.__name__.split('.')[-1].upper()}")
    
    # Template JSON selon le format
    nom_format   = fmt.__name__.split(".")[-1]
    template     = TEMPLATES.get(nom_format)
    
    # Extraire
    entete       = fmt.extraire_entete(chemin_pdf, template)
    lignes       = fmt.extraire_positions(chemin_pdf)
    output_df    = fmt.formater_output(lignes)
    
    # Exporter
    exporter_excel(output_df, entete, chemin_pdf)
    print("✅ Terminé !")

# ── Lancer ──
traiter_pdf("pdfs/Athens_Derivatives_Statement.pdf")
# traiter_pdf("pdfs/morgan_stanley.pdf")  # décommentez pour tester Morgan