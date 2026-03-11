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

            # ── Utiliser extract_words() avec positions Y ──
            words = page.extract_words()

            # Regrouper les mots par ligne (coordonnée Y arrondie)
            lignes_mots = {}
            for w in words:
                y = round(w['top'], 1)
                if y not in lignes_mots:
                    lignes_mots[y] = []
                lignes_mots[y].append(w)

            # Trouver les positions X des colonnes depuis l'entête
            col_x = {}
            for y in sorted(lignes_mots.keys()):
                mots = lignes_mots[y]
                texte_ligne = " ".join(w['text'] for w in mots)
                if "LONG" in texte_ligne and "SHORT" in texte_ligne and "TRADE" in texte_ligne:
                    for w in mots:
                        col_x[w['text'].upper()] = w['x0']
                    print(f"   Entête trouvée : {texte_ligne}")
                    print(f"   Positions X : {col_x}")
                    break

            # Trouver Contract et Maturity
            current_contract = ""
            current_maturity = ""
            mon = yr = ""

            dans_bloc = False

            for y in sorted(lignes_mots.keys()):
                mots = lignes_mots[y]
                texte_ligne = " ".join(w['text'] for w in mots)

                # Début du bloc
                if "OPEN POSITIONS STATEMENT" in texte_ligne:
                    dans_bloc = True
                    continue

                if not dans_bloc:
                    continue

                # Fin du bloc
                if "TOTAL" in texte_ligne and "FUTURES" in texte_ligne:
                    break

                # Ignorer entêtes et totaux
                if any(x in texte_ligne for x in [
                    "CONTRACT", "MATURITY", "SETTLEMENT", "TOTAL", "NO POSITIONS"
                ]):
                    # Chercher Contract (FTASE25 etc.)
                    for w in mots:
                        if re.match(r'^[A-Z]{3,}[0-9]{2}$', w['text']):
                            current_contract = w['text']
                    # Chercher Maturity (FEB 2026)
                    m = re.search(r'([A-Z]{3})\s+(\d{4})', texte_ligne)
                    if m:
                        mon = m.group(1)
                        yr  = m.group(2)
                    continue

                # ── Lignes de données : contiennent une date DD/MM/YY ──
                dates    = [w for w in mots if re.match(r'\d{2}/\d{2}/\d{2}', w['text'])]
                numbers  = [w for w in mots if re.match(r'^\d+$', w['text'])]

                if not dates or not numbers:
                    continue

                # Extraire Trade Date et Trade Number
                # Trade Date = premier mot date
                # Trade Number = premier grand nombre (8 chiffres)
                trade_date   = ""
                trade_number = ""
                long_val     = ""
                short_val    = ""

                for w in mots:
                    # Date : DD/MM/YY
                    if re.match(r'\d{2}/\d{2}/\d{2}', w['text']) and not trade_date:
                        trade_date = w['text']

                    # Trade Number : 8 chiffres
                    if re.match(r'^\d{8}$', w['text']) and not trade_number:
                        trade_number = w['text']

                    # Long/Short : petit nombre (2-3 chiffres) selon position X
                    if re.match(r'^\d{1,4}$', w['text']) and w['text'] != trade_number:
                        # Déterminer si Long ou Short selon position X
                        if col_x:
                            long_x  = col_x.get("LONG",  200)
                            short_x = col_x.get("SHORT", 250)
                            if abs(w['x0'] - long_x) < abs(w['x0'] - short_x):
                                if not long_val:
                                    long_val = w['text']
                            else:
                                if not short_val:
                                    short_val = w['text']
                        else:
                            if not long_val:
                                long_val = w['text']

                if not trade_date or not trade_number:
                    continue

                ligne = {
                    "Trade Date":   trade_date,
                    "Trade Number": trade_number,
                    "Long":         long_val,
                    "Short":        short_val,
                    "Product":      current_contract,
                    "Mon":          mon,
                    "Yr":           yr,
                    "CCY":          "EUR",
                }
                toutes_les_lignes.append(ligne)
                print(f"  ✅ {ligne}")

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
