import re

def detecter(texte_page1):
    """Retourne True si c'est un PDF Triton"""
    return "OPEN POSITIONS STATEMENT" in texte_page1

def extraire_entete(chemin_pdf, template_json=None):
    import pdfplumber, json, os
    with pdfplumber.open(chemin_pdf) as pdf:
        lignes = pdf.pages[0].extract_text().split("\n")

    infos = {"Broker": "", "Client": "", "Close of Business": "", "Account": ""}

    if template_json and os.path.exists(template_json):
        with open(template_json) as f:
            infos.update(json.load(f))

    for ligne in lignes:
        ligne = ligne.strip()
        m = re.search(r'ACCOUNT\s*:\s*(\S+)', ligne)
        if m and not infos["Account"]:
            infos["Account"] = m.group(1).strip()
        m = re.search(r'ATHENS\s*,\s*(\d{2}/\d{2}/\d{2})', ligne)
        if m and not infos["Close of Business"]:
            infos["Close of Business"] = m.group(1).strip()
        if "Derivatives" in ligne and not infos["Broker"]:
            infos["Broker"] = ligne.strip()
        if not infos["Client"] and re.match(r'^[A-Z]', ligne):
            if not any(x in ligne for x in ["STATEMENT","Athens","ACCOUNT","ATHENS","VALAORITOU"]):
                infos["Client"] = ligne.strip()

    print(f"\n✅ Entête Triton : {infos}")
    return infos


def extraire_positions(chemin_pdf):
    toutes_les_lignes = []

    with pdfplumber.open(chemin_pdf) as pdf:
        for i, page in enumerate(pdf.pages):
            texte = page.extract_text()
            if not texte or "OPEN POSITIONS STATEMENT" not in texte:
                continue

            print(f"\n✅ OPEN POSITIONS trouvé - Page {i+1}")

            words = page.extract_words()

            # Regrouper mots par Y
            lignes_mots = {}
            for w in words:
                y = round(w['top'], 1)
                if y not in lignes_mots:
                    lignes_mots[y] = []
                lignes_mots[y].append(w)

            # Trouver position X de LONG et SHORT depuis entête
            long_x  = None
            short_x = None
            trade_number_x = None

            for y in sorted(lignes_mots.keys()):
                mots = lignes_mots[y]
                texte_ligne = " ".join(w['text'] for w in mots)
                if "LONG" in texte_ligne and "SHORT" in texte_ligne and "NUMBER" in texte_ligne:
                    for w in mots:
                        if w['text'] == "LONG":
                            long_x = w['x0']
                        if w['text'] == "SHORT":
                            short_x = w['x0']
                        if w['text'] == "NUMBER":
                            trade_number_x = w['x0']
                    print(f"   LONG x={long_x}, SHORT x={short_x}, NUMBER x={trade_number_x}")
                    break

            if not long_x or not short_x:
                continue

            dans_bloc = False

            for y in sorted(lignes_mots.keys()):
                mots = lignes_mots[y]
                texte_ligne = " ".join(w['text'] for w in mots)

                if "OPEN POSITIONS STATEMENT" in texte_ligne:
                    dans_bloc = True
                    continue

                if not dans_bloc:
                    continue

                if any(x in texte_ligne for x in ["TOTAL", "CONTRACT", "MATURITY", "SETTLEMENT", "NO POSITIONS"]):
                    continue

                # Ligne de données : doit contenir une date DD/MM/YY et un Trade Number (8 chiffres)
                dates   = [w for w in mots if re.match(r'^\d{2}/\d{2}/\d{2}$', w['text'])]
                numbers = [w for w in mots if re.match(r'^\d{8}$', w['text'])]

                if not dates or not numbers:
                    continue

                trade_date   = dates[0]['text']
                trade_number = numbers[0]['text']
                long_val     = ""
                short_val    = ""

                # Chercher Long/Short selon position X
                for w in mots:
                    # Ignorer dates et trade number
                    if re.match(r'^\d{2}/\d{2}/\d{2}$', w['text']): continue
                    if re.match(r'^\d{8}$', w['text']): continue
                    # Ignorer grands nombres (prix ex: 5 627.75)
                    if re.match(r'^\d{1,3}\.\d+$', w['text']): continue

                    # Petits nombres = quantités
                    if re.match(r'^\d{1,4}$', w['text']):
                        dist_long  = abs(w['x0'] - long_x)
                        dist_short = abs(w['x0'] - short_x)
                        if dist_long < dist_short:
                            if not long_val:
                                long_val = w['text']
                        else:
                            if not short_val:
                                short_val = w['text']

               ligne = {
                    "Trade Date":   trade_date,
                    "Trade Number": trade_number,
                    "Long":         long_val,
                    "Short":        short_val,
                }
                toutes_les_lignes.append(ligne)
                print(f"  ✅ {trade_date} | {trade_number} | Long={long_val} | Short={short_val}")

    print(f"\n📊 Triton - Total lignes : {len(toutes_les_lignes)}")
    return toutes_les_lignes

def formater_output(lignes):
    """Retourne un DataFrame détaillé (pas d'agrégation pour Triton)"""
    import pandas as pd
    df = pd.DataFrame(lignes)
    df["Long"]  = pd.to_numeric(df["Long"],  errors="coerce").fillna(0).astype(int)
    df["Short"] = pd.to_numeric(df["Short"], errors="coerce").fillna(0).astype(int)
    df["Long"]  = df["Long"].replace(0, "")
    df["Short"] = df["Short"].replace(0, "")

    return df[["Trade Date", "Trade Number", "Long", "Short"]]

