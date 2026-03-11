python -c "
import pdfplumber
with pdfplumber.open('pdfs/Athens_Derivatives_Statement.pdf') as pdf:
    page = pdf.pages[0]
    words = page.extract_words()
    # Afficher les mots avec leurs coordonnées Y
    for w in words:
        print(f'y={round(w[\"top\"],1):6} | x={round(w[\"x0\"],1):6} | {w[\"text\"]}')
" | head -80
