from formats import morgan, triton, baml

FORMATS = [triton, baml, morgan]  # du plus spécifique au plus général

def detecter_format(chemin_pdf):
    with pdfplumber.open(chemin_pdf) as pdf:
        texte = pdf.pages[0].extract_text() or ""
    for fmt in FORMATS:
        if fmt.detecter(texte):
            return fmt
    return None
