python -c "
import pdfplumber
with pdfplumber.open('pdfs/Athens_Derivatives_Statement.pdf') as pdf:
    page = pdf.pages[0]
    words = page.extract_words()
    # Afficher les mots avec leurs coordonnées Y
    for w in words:
        print(f'y={round(w[\"top\"],1):6} | x={round(w[\"x0\"],1):6} | {w[\"text\"]}')
" | head -80



                         python -c "
import pdfplumber
p = r'T:\Dallas\CSS-BOC\CTL\REC\Réconciliation dérivés listés\20UGS\2026\01. JANVIER\PIRAEUS BANK\TRITON.PDF'
with pdfplumber.open(p) as pdf:
    for i, page in enumerate(pdf.pages):
        tables = page.extract_tables()
        print(f'--- PAGE {i+1} : {len(tables)} tableau(x) ---')
        for t in tables:
            for row in t:
                print(row)
"
