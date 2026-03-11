import pdfplumber
import re
import pandas as pd

def detecter(texte):
    return "MERRILL LYNCH INTERNATIONAL" in texte

def extraire_entete(chemin_pdf, template_json=None):
    infos = {
        "Broker":            "MERRILL LYNCH INTERNATIONAL",
        "Client":            "",
        "Account":           "",
        "Close of Business": ""
    }
    with pdfplumber.open(chemin_pdf) as pdf:
        texte = pdf.pages[0].extract_text() or ""
        for ligne in texte.split('\n'):
            m = re.search(r'ACCOUNT NUMBER:\s*(\S+)', ligne)
            if m and not infos["Account"]:
                infos["Account"] = m.group(1).strip()
            m = re.search(r'STATEMENT DATE:\s*(.+)', ligne)
            if m and not infos["Close of Business"]:
                infos["Close of Business"] = m.group(1).strip()
        lignes = texte.split('\n')
        for i, ligne in enumerate(lignes):
            if "MORGAN STANLY" in ligne or "MORGAN STANLEY" in ligne:
                client_parts = []
                for j in range(i, min(i+4, len(lignes))):
                    l = lignes[j].strip()
                    if l and not any(x in l for x in ["CABOT","LONDON","UNITED","PAGE"]):
                        client_parts.append(l)
                infos["Client"] = " ".join(client_parts)
                break
    print(f"✅ Entête BAML : {infos}")
    return infos

def extraire_positions(chemin_pdf):
    toutes_les_lignes = []

    with pdfplumber.open(chemin_pdf) as pdf:
        for i, page in enumerate(pdf.pages):
            words = page.extract_words()
            if not words:
                continue

            lignes_mots = {}
            for w in words:
                y = round(w['top'], 1)
                if y not in lignes_mots:
                    lignes_mots[y] = []
                lignes_mots[y].append(w)

            # Chercher entête LONG/SHORT
            long_x = short_x = trade_x = contract_x = header_y = None
            for y in sorted(lignes_mots.keys()):
                mots = lignes_mots[y]
                texte_ligne = " ".join(w['text'] for w in mots)
                if ("LONG" in texte_ligne and "SHORT" in texte_ligne
                        and "TRADE" in texte_ligne and "CONTRACT" in texte_ligne):
                    for w in mots:
                        if w['text'] == "TRADE":    trade_x    = w['x0']
                        if w['text'] == "LONG":     long_x     = w['x0']
                        if w['text'] == "SHORT":    short_x    = w['x0']
                        if w['text'] == "CONTRACT": contract_x = w['x0']
                    header_y = y
                    print(f"\n✅ Page {i+1} - TRADE x={trade_x:.1f} LONG x={long_x:.1f} SHORT x={short_x:.1f} CONTRACT x={contract_x:.1f}")
                    break

            if not long_x or not header_y:
                continue

            TOL = 25
            ys_sorted = [y for y in sorted(lignes_mots.keys()) if y > header_y]

            # Mémoriser le dernier contract vu sur une ligne de données
            last_contract = ""

            for y in ys_sorted:
                mots = lignes_mots[y]
                texte_ligne = " ".join(w['text'] for w in mots)

                # Ignorer AVG, PAGE, entêtes système
                if any(x in texte_ligne for x in [
                    "AVG ", "CLOSE", "PAGE", "MERRILL", "FUTURES", "KING",
                    "LONDON", "MORGAN", "FUND", "FCH", "CABOT", "UNITED",
                    "KINGDOM", "CONFIRMATION", "ACCEPTED", "PURCHASE",
                    "SALE", "------", "SETTL", "DEBIT", "COMMISSION",
                    "NET PROFIT", "GROSS", "CLEARING", "BROKERAGE",
                    "OPEN TRADE", "OPTION"
                ]):
                    continue

                # ── Ligne TOTAL : contient N* ──
                total_match = re.search(r'\b(\d+)\*', texte_ligne)
                if total_match:
                    long_val  = ""
                    short_val = ""
                    for w in mots:
                        if re.match(r'^\d+\*$', w['text']):
                            val = w['text'].replace('*', '')
                            dist_long  = abs(w['x0'] - long_x)
                            dist_short = abs(w['x0'] - short_x)
                            if dist_long < dist_short:
                                long_val  = val
                            else:
                                short_val = val

                    if not long_val and not short_val:
                        continue

                    # ── Capturer la valeur TRADE (mot numérique le plus proche de trade_x) ──
                    trade_val = ""
                    if trade_x is not None:
                        best_dist = float('inf')
                        for w in mots:
                            if re.match(r'^\d+\*?$', w['text']):
                                dist = abs(w['x0'] - trade_x)
                                if dist < best_dist:
                                    best_dist = dist
                                    trade_val = w['text'].replace('*', '')

                    # Parser contract : "06 MAR 26 EUR EUR-BUND"
                    mon = yr = product = ccy = ""
                    mc = re.search(r'([A-Z]{3})\s+(\d{2})\s+(?:([A-Z]{2,3})\s+)?(.+)', last_contract)
                    if mc:
                        mon     = mc.group(1)
                        yr      = mc.group(2)
                        ccy     = mc.group(3) or ""
                        product = mc.group(4).strip()
                    else:
                        product = last_contract

                    ligne_data = {
                        "Trade Date":  "",
                        "Trade":       trade_val,
                        "Long":        long_val,
                        "Short":       short_val,
                        "Product":     product,
                        "Mon":         mon,
                        "Yr":          yr,
                        "CCY":         ccy,
                    }
                    toutes_les_lignes.append(ligne_data)
                    print(f"  ✅ Trade={trade_val} | Long={long_val} | Short={short_val} | {product} {mon} {yr} {ccy}")
                    continue

                # ── Ligne de données : mémoriser contract ──
                # Contract = mots à x >= contract_x, avant le prix (grand nombre décimal)
                contract_parts = []
                for w in mots:
                    if w['x0'] >= contract_x - TOL:
                        txt = w['text']
                        # Arrêter au prix (format 27 ou grand nombre)
                        if re.match(r'^\d{3,}[\.,]', txt):
                            break
                        if re.match(r'^\d{1,3}$', txt) and float(txt) > 26:
                            break  # c'est le EX (ex: 27)
                        contract_parts.append(txt)

                if contract_parts:
                    last_contract = " ".join(contract_parts).strip()

    print(f"\n📊 BAML - Total : {len(toutes_les_lignes)} positions")
    return toutes_les_lignes


def formater_output(lignes):
    df = pd.DataFrame(lignes)
    if df.empty:
        return df

    df["Trade"] = pd.to_numeric(df["Trade"], errors="coerce").fillna(0).astype(int)
    df["Long"]  = pd.to_numeric(df["Long"],  errors="coerce").fillna(0).astype(int)
    df["Short"] = pd.to_numeric(df["Short"], errors="coerce").fillna(0).astype(int)

    resume = df.groupby(["Product", "CCY", "Mon", "Yr"], as_index=False).agg(
        Total_Trade=("Trade", "sum"),
        Total_Long =("Long",  "sum"),
        Total_Short=("Short", "sum")
    )
    resume["Total_Trade"] = resume["Total_Trade"].replace(0, "")
    resume["Total_Long"]  = resume["Total_Long"].replace(0, "")
    resume["Total_Short"] = resume["Total_Short"].replace(0, "")
    return resume[["Product", "Total_Trade", "Total_Long", "Total_Short", "CCY", "Mon", "Yr"]]
