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
                    if l and not any(x in l for x in ["CABOT","LONDON","UNITED","PAGE"]):
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


def extraire_positions(chemin_pdf):
    toutes_les_lignes = []

    with pdfplumber.open(chemin_pdf) as pdf:
        last_header_found = False
        last_contract     = ""
        last_trade_date   = ""
        last_cc           = ""
        pending_total     = None

        for i, page in enumerate(pdf.pages):
            texte = page.extract_text()
            if not texte:
                continue

            lignes = texte.split('\n')

            # Chercher header sur cette page
            header_idx = None
            for j, ligne in enumerate(lignes):
                if ("LONG" in ligne and "SHORT" in ligne
                        and "TRADE" in ligne and "CONTRACT" in ligne):
                    header_idx = j
                    last_header_found = True
                    print(f"\n✅ Page {i+1} - header trouvé")
                    break

            if header_idx is None:
                if last_header_found:
                    print(f"\n✅ Page {i+1} - continuation")
                    header_idx = -1
                else:
                    continue

            start_idx = header_idx + 2 if header_idx >= 0 else 0
            data_lignes = lignes[start_idx:]

            for ligne in data_lignes:
                stripped = ligne.strip()
                if not stripped:
                    continue

                # ── AVG LONG / AVG SHORT → résoudre pending ──
                if stripped.startswith("AVG LONG:") or stripped.startswith("AVG SHORT:"):
                    if pending_total:
                        long_val  = pending_total["val"] if "LONG"  in stripped else ""
                        short_val = pending_total["val"] if "SHORT" in stripped else ""
                        toutes_les_lignes.append({
                            "Trade Date": last_trade_date,
                            "Long":       long_val,
                            "Short":      short_val,
                            "Product":    pending_total["product"],
                            "Mon":        pending_total["mon"],
                            "Yr":         pending_total["yr"],
                            "CCY":        pending_total["ccy"],
                        })
                        print(f"  ✅ {last_trade_date} | L={long_val} | S={short_val} | {pending_total['product']}")
                        pending_total = None
                    # Reset contract après chaque bloc
                    last_contract = ""
                    continue

                # ── Ligne TOTAL : N* ──
                if re.match(r'^[\d,\.]+\*', stripped):
                    if any(x in stripped for x in [
                        "COMMISSION", "GROSS", "CONVERTED", "NET PROFIT", "SEC"
                    ]):
                        continue

                    total_m = re.match(r'^([\d,\.]+)\*', stripped)
                    if not total_m or not last_contract:
                        continue

                    val = total_m.group(1).replace(',', '').replace('.', '')

                    mon = yr = ""
                    mc = re.search(r'([A-Z]{3})\s+(\d{2})\b', last_contract)
                    if mc:
                        mon = mc.group(1)
                        yr  = mc.group(2)
                    product = last_contract
                    ccy     = last_cc

                    # Cas 1 : N* CLOSE sans EX → attendre AVG
                    if "CLOSE" in stripped and not re.search(r'EX[-\s]', stripped):
                        pending_total = {
                            "val": val, "product": product,
                            "mon": mon, "yr": yr, "ccy": ccy,
                        }

                    # Cas 2 : N* EX-... CLOSE → Long par défaut + reset
                    elif re.search(r'EX[-\s]', stripped) and "CLOSE" in stripped:
                        toutes_les_lignes.append({
                            "Trade Date": last_trade_date,
                            "Long":       val,
                            "Short":      "",
                            "Product":    product,
                            "Mon":        mon,
                            "Yr":         yr,
                            "CCY":        ccy,
                        })
                        print(f"  ✅ {last_trade_date} | L={val} | S= | {product} {mon} {yr} {ccy}")
                        last_contract = ""  # Reset après bloc

                    continue

                # Ignorer lignes système
                if any(x in ligne for x in [
                    "MERRILL", "FUTURES", "KING EDWARD", "LONDON",
                    "MORGAN", "FUND", "FCH", "CABOT", "UNITED", "KINGDOM",
                    "CONFIRMATION", "ACCEPTED", "PURCHASE", "SALE",
                    "COMMISSION", "NET PROFIT", "GROSS", "CLEARING",
                    "BROKERAGE", "OPEN TRADE", "* REG", "* SEC",
                    "OPTION", "CONVERTED", "CLOSE", "------",
                    "TRADING UNIT", "PAGE", "STATEMENT DATE",
                    "BEGINNING BALANCE", "TOTAL FEES", "NFA FEES",
                    "PRICE ALIGN", "LCH SWAP", "GBP VM",
                    "SWAP COMPOUND", "O P E N", "C O N F"
                ]):
                    continue

                # ── Ligne de données futures ──
                # Format: "12/05/5 F4 3 06 MAR 26 EUR EUR-BUND 27 128.2 EU 90.00DR"
                m = re.match(
                    r'^(\d{1,2}/\d{1,2}/\d{1,2})\s+'  # date
                    r'\w+\s+'                            # SETTL
                    r'\w+\s+'                            # AT
                    r'[\d,]+\s+'                         # quantité
                    r'(.+?)\s+'                          # contract TEL QUEL
                    r'\d+\s+'                            # EX (2 chiffres)
                    r'[\d\.\-]+\s+'                      # PRICE
                    r'([A-Z]{2})\b',                    # CC
                    stripped
                )
                if m:
                    last_trade_date = m.group(1)
                    last_contract   = m.group(2).strip()
                    last_cc         = m.group(3).strip()
                    continue

                # ── Ligne de données CDS ──
                # Format: "9/29/5 Q1 28,000 CDS JUN 30 CDXEMS43V1 100 9L US 145,755.56"
                m_cds = re.match(
                    r'^(\d{1,2}/\d{1,2}/\d{1,2})\s+'  # date
                    r'\w+\s+'                            # SETTL
                    r'[\d,]+\s+'                         # quantité
                    r'(.+?)\s+'                          # contract TEL QUEL
                    r'(US|EU)\s+',                      # CC
                    stripped
                )
                if m_cds:
                    last_trade_date = m_cds.group(1)
                    last_contract   = m_cds.group(2).strip()
                    last_cc         = m_cds.group(3).strip()

    print(f"\n📊 BAML - Total : {len(toutes_les_lignes)} positions")
    return toutes_les_lignes


def formater_output(lignes):
    """Pas de groupby — retourner lignes brutes"""
    df = pd.DataFrame(lignes)
    if df.empty:
        return df
    df["Long"]  = pd.to_numeric(df["Long"],  errors="coerce").fillna(0).astype(int)
    df["Short"] = pd.to_numeric(df["Short"], errors="coerce").fillna(0).astype(int)
    df["Long"]  = df["Long"].replace(0,  "")
    df["Short"] = df["Short"].replace(0, "")
    return df[["Trade Date", "Long", "Short", "Product", "Mon", "Yr", "CCY"]]
