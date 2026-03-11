python -c "
import pdfplumber
p = r'T:\Dallas\CSS-BOC\CTL\REC\Réconciliation dérivés listés\FUND CHANNEL\2026\BAML\MSIM_SG_EOD Daily Statement.pdf'
with pdfplumber.open(p) as pdf:
    for i, page in enumerate(pdf.pages):
        texte = page.extract_text() or ''
        if 'OPEN POSITIONS' in texte:
            print(f'--- PAGE {i+1} ---')
            for j, ligne in enumerate(texte.split('\n')):
                print(f'[{j}] {ligne}')
            print()
            break  # juste la premiere page OPEN POSITIONS
"
