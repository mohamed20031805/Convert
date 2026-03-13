import pdfplumber
import re
import pandas as pd


def detecter(texte):
    return (
        "SOCIETE GENERALE" in texte and
        "POSITIONS OUVERTES" in texte
    )


def extraire_entete(chemin_pdf, template_json=None):
    infos = {
        "Broker":            "SOCIETE GENERALE",
        "Client":            "",
        "Account":           "",
        "Close of Business": ""
    }
    with pdfplumber.open(chemin_pdf) as pdf:
        texte = pdf.pages[0].extract_text() or ""
        for ligne in texte.split('\n'):
            m = re.search(r'NUMERO DE COMPTE\s*:\s*(.+)', ligne)
            if m:
                infos["Account"] = m.group(1).strip()
            m = re.search(r'DATE\s*:\s*(.+)', ligne)
            if m and not infos["Close of Business"]:
                infos["Close of Business"] = m.group(1).strip()

        # Client = lignes entre adresse SG et ATTN
        lignes  = texte.split('\n')
        capture = False
        parts   = []
        for ligne in lignes:
            l = ligne.strip()
            if "PARIS LA DEFENSE" in l or "COURS VALMY" in l:
                capture = True
                continue
            if capture:
                if any(x in l for x in ["ATTN", "COMPTE DISCRETION"]):
                    break
                if l and not any(x in l for x in [
                    "28 32", "L-1616", "LUXEMBOURG", "LA GARE"
                ]):
                    parts.append(l)
        infos["Client"] = " - ".join(parts)

    return infos


def extraire_positions(chemin_pdf):
    toutes = []

    with pdfplumber.open(chemin_pdf) as pdf:
        for i, page in enumerate(pdf.pages):
            texte = page.extract_text()
            if not texte or "POSITIONS OUVERTES" not in texte:
                continue

            lignes = texte.split('\n')

            # Header: DATE VALEUR DV ACHAT VENTE DESCRIPTION...
            header_idx = None
            for j, l in enumerate(lignes):
                if "ACHAT" in l and "VENTE" in l and "DESCRIPTION" in l:
                    header_idx = j
                    break

            if header_idx is None:
                continue

            last_contract   = ""
            last_trade_date = ""
            last_cc         = ""
            pending_total   = None

            for ligne in lignes[header_idx + 2:]:
                stripped = ligne.strip()
                if not stripped:
                    continue

                if any(x in ligne for x in [
                    "SOLDE INITIAL", "SOLDE FINAL", "VALORISATION",
                    "LME TRADES", "DERIVATIVE", "DOLLAR US",
                    "YEN JAPONAIS", "------"
                ]):
                    break

                # AVG LONG / AVG SHORT
                if stripped.startswith("AVG LONG:") or stripped.startswith("AVG SHORT:"):
                    if pending_total:
                        long_val  = pending_total["val"] if "LONG"  in stripped else ""
                        short_val = pending_total["val"] if "SHORT" in stripped else ""
                        toutes.append({
                            "Trade Date": last_trade_date,
                            "Long":       long_val,
                            "Short":      short_val,
                            "Product":    pending_total["product"],
                            "Mon":        pending_total["mon"],
                            "Yr":         pending_total["yr"],
                            "CCY":        pending_total["ccy"],
                        })
                        pending_total = None
                    last_contract = ""
                    continue

                # Ligne TOTAL : N* ...CLOSE
                if re.match(r'^[\d,]+\*', stripped):
                    total_m = re.match(r'^([\d,]+)\*', stripped)
                    if not total_m or not last_contract:
                        continue
                    val = total_m.group(1).replace(',', '')
                    mon = yr = ""
                    mc = re.search(r'([A-Z]{3})\s+(\d{2})\b', last_contract)
                    if mc:
                        mon = mc.group(1)
                        yr  = mc.group(2)
                    pending_total = {
                        "val": val, "product": last_contract,
                        "mon": mon, "yr": yr, "ccy": last_cc,
                    }
                    continue

                # Ligne données
                # "22MAY25 22MAY25 E1 125  CALL PANW 18 JUN 26 185.00 SG 32.5933 US"
                m = re.match(
                    r'^(\w+)\s+'        # DATE
                    r'\w+\s+'           # VALEUR
                    r'\w+\s+'           # DV
                    r'([\d,]+)\s+'      # ACHAT (Long)
                    r'(.+?)\s+'         # DESCRIPTION
                    r'\w+\s+'           # EX
                    r'[\d\.]+\s+'       # PRIX
                    r'([A-Z]{2})\b',    # CC
                    stripped
                )
                if m:
                    last_trade_date = m.group(1)
                    last_contract   = m.group(3).strip()
                    last_cc         = m.group(4).strip()

    return toutes


def formater_output(lignes):
    df = pd.DataFrame(lignes)
    if df.empty:
        return pd.DataFrame(columns=[
            "Trade Date", "Long", "Short", "Product", "Mon", "Yr", "CCY"
        ])
    df["Long"]  = pd.to_numeric(df["Long"],  errors="coerce").fillna(0).astype(int)
    df["Short"] = pd.to_numeric(df["Short"], errors="coerce").fillna(0).astype(int)
    df["Long"]  = df["Long"].replace(0,  "")
    df["Short"] = df["Short"].replace(0, "")
    return df[["Trade Date", "Long", "Short", "Product", "Mon", "Yr", "CCY"]]
