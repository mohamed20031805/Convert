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
                for j in range(i, min(i + 4, len(lignes))):
                    l = lignes[j].strip()
                    if l and not any(x in l for x in ["CABOT", "LONDON", "UNITED", "PAGE"]):
                        client_parts.append(l)
                infos["Client"] = " ".join(client_parts)
                break

    if template_json:
        import json, os
        if os.path.exists(template_json):
            with open(template_json) as f:
                t = json.load(f)
            for k, v in t.items():
                if not infos.get(k):
                    infos[k] = v

    print(f"✅ Entête BAML : {infos}")
    return infos


# Positions fixes des colonnes (basées sur les tirets)
COL_TRADE    = (0,  6)
COL_LONG     = (15, 20)
COL_SHORT    = (20, 26)
COL_CONTRACT = (26, 47)
COL_CC       = (56, 58)


def get_col(ligne, start, end):
    """Extraire une colonne par position de caractères"""
    if len(ligne) < start:
        return ""
    return ligne[start:end].strip()


def extraire_positions(chemin_pdf):
    toutes_les_lignes = []

    with pdfplumber.open(chemin_pdf) as pdf:
        for i, page in enumerate(pdf.pages):
            texte = page.extract_text()
            if not texte:
                continue

            lignes = texte.split('\n')

            # Chercher la ligne d'entête TRADE LONG SHORT CONTRACT
            header_idx = None
            for j, ligne in enumerate(lignes):
                if ("LONG" in ligne and "SHORT" in ligne
                        and "TRADE" in ligne and "CONTRACT" in ligne
                        and "DESCRIPTION" in ligne):
                    header_idx = j
                    print(f"\n✅ Page {i+1} - entête ligne {j}")
                    break

            if header_idx is None:
                continue

            last_contract   = ""
            last_trade_date = ""
            last_cc         = ""

            for ligne in lignes[header_idx + 2:]:  # +2 pour sauter les tirets

                # Ignorer lignes système
                if any(x in ligne for x in [
                    "AVG ", "PAGE", "MERRILL", "FUTURES", "KING",
                    "LONDON", "MORGAN", "FUND", "FCH", "CABOT", "UNITED",
                    "KINGDOM", "CONFIRMATION", "ACCEPTED", "PURCHASE",
                    "SALE", "SETTL", "DEBIT", "COMMISSION",
                    "NET PROFIT", "GROSS", "CLEARING", "BROKERAGE",
                    "OPEN TRADE", "OPTION", "TRADE SETTL"
                ]):
                    continue

                # ── Ligne TOTAL : commence par N* ex "27* CLOSE" ──
                total_match = re.match(r'^([\d,\.]+)\*', ligne.strip())
                if total_match:
                    val = total_match.group(1).replace(',', '').replace('.', '')

                    # Déterminer Long ou Short selon position du N*
                    # Le N* est dans la colonne LONG (pos 15-20) ou SHORT (pos 20-26)
                    pos_etoile = ligne.index('*')
                    long_val  = ""
                    short_val = ""

                    if COL_LONG[0] <= pos_etoile <= COL_LONG[1] + 5:
                        long_val  = val
                    elif COL_SHORT[0] <= pos_etoile <= COL_SHORT[1] + 5:
                        short_val = val
                    else:
                        # Par défaut chercher lequel est le plus proche
                        dist_long  = abs(pos_etoile - COL_LONG[0])
                        dist_short = abs(pos_etoile - COL_SHORT[0])
                        if dist_long < dist_short:
                            long_val  = val
                        else:
                            short_val = val

                    if not long_val and not short_val:
                        continue

                    # Parser contract : "06 MAR 26 EUR EUR-BUND"
                    mon = yr = product = ccy = ""
                    mc = re.search(
                        r'\d{2}\s+([A-Z]{3})\s+(\d{2})\s+(?:([A-Z]{2,3})\s+)?(.+)',
                        last_contract
                    )
                    if mc:
                        mon     = mc.group(1)
                        yr      = mc.group(2)
                        ccy     = last_cc or mc.group(3) or ""
                        product = mc.group(4).strip()
                    else:
                        mc2 = re.search(
                            r'([A-Z]{3})\s+(\d{2})\s+(?:([A-Z]{2,3})\s+)?(.+)',
                            last_contract
                        )
                        if mc2:
                            mon     = mc2.group(1)
                            yr      = mc2.group(2)
                            ccy     = last_cc or mc2.group(3) or ""
                            product = mc2.group(4).strip()
                        else:
                            product = last_contract
                            ccy     = last_cc

                    ligne_data = {
                        "Trade Date": last_trade_date,
                        "Long":       long_val,
                        "Short":      short_val,
                        "Product":    product,
                        "Mon":        mon,
                        "Yr":         yr,
                        "CCY":        ccy,
                    }
                    toutes_les_lignes.append(ligne_data)
                    print(f"  ✅ {last_trade_date} | Long={long_val} | Short={short_val} | {product} {mon} {yr} {ccy}")
                    continue

                # Ignorer CLOSE
                if ligne.strip().startswith("CLOSE"):
                    continue

                # ── Ligne de données : extraire par position ──
                trade_date = get_col(ligne, *COL_TRADE)
                contract   = get_col(ligne, *COL_CONTRACT)
                cc         = get_col(ligne, *COL_CC)

                # Valider trade date format MM/DD/Y
                if re.match(r'^\d{1,2}/\d{1,2}/\d{1,2}$', trade_date) and contract:
                    last_trade_date = trade_date
                    last_contract   = contract
                    last_cc         = cc

    print(f"\n📊 BAML - Total : {len(toutes_les_lignes)} positions")
    return toutes_les_lignes


def formater_output(lignes):
    df = pd.DataFrame(lignes)
    if df.empty:
        return df

    df["Long"]  = pd.to_numeric(df["Long"],  errors="coerce").fillna(0).astype(int)
    df["Short"] = pd.to_numeric(df["Short"], errors="coerce").fillna(0).astype(int)

    resume = df.groupby(["Product", "CCY", "Mon", "Yr"], as_index=False).agg(
        Total_Long =("Long",  "sum"),
        Total_Short=("Short", "sum")
    )
    resume["Total_Long"]  = resume["Total_Long"].replace(0, "")
    resume["Total_Short"] = resume["Total_Short"].replace(0, "")
    return resume[["Product", "Total_Long", "Total_Short", "CCY", "Mon", "Yr"]]
