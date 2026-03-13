import pandas as pd
import re
import json
import os

ACCOUNTS_JSON = "templates/accounts.json"

# ── Mapping produit PDF → mots clés client ──
MAPPING_DIRECT = {
    "EURO FX":      "EURO FX",
    "IMM EURO":     "EURO FX",
    "SWISS FRANC":  "CHF CURRENCY",
    "SF ":          "CHF CURRENCY",
    "EUR/CHF":      "EUR/CHF",
    "IMM SF":       "CHF CURRENCY",
}


def normaliser(texte):
    return re.sub(r'[^A-Z0-9]', '', str(texte).upper())


def lire_desc_port(df_raw):
    """Lire Desc.Port. depuis ligne 4 (index 3) colonne D (index 3)"""
    try:
        row = df_raw.iloc[3]
        # Chercher la valeur après "Desc. Port."
        valeurs = [str(v).strip() for v in row if pd.notna(v)
                   and str(v).strip() not in ["", "nan", "Desc. Port."]]
        # La valeur est après "Desc. Port." dans la même ligne
        row_list = list(row)
        for i, v in enumerate(row_list):
            if "Desc" in str(v) and "Port" in str(v):
                # Valeur suivante non nulle
                for j in range(i+1, len(row_list)):
                    if pd.notna(row_list[j]) and str(row_list[j]).strip() not in ["", "nan"]:
                        return str(row_list[j]).strip()
    except Exception:
        pass
    return ""


def charger_client(chemin_excel):
    """
    Charger tous les onglets du fichier client SG.
    Retourne dict: {desc_port: df_positions}
    """
    xl      = pd.ExcelFile(chemin_excel)
    onglets = {}

    for sheet in xl.sheet_names:
        try:
            df_raw  = pd.read_excel(xl, sheet_name=sheet, header=None)
            desc    = lire_desc_port(df_raw)
            if not desc or desc == "nan":
                continue

            # Header ligne 9 (index 8)
            df = pd.read_excel(xl, sheet_name=sheet, header=8)
            df.columns = [str(c).strip() for c in df.columns]

            # Garder lignes avec Descrizione
            col_desc = next(
                (c for c in df.columns if "Descri" in c), None
            )
            col_qta = next(
                (c for c in df.columns if c == "Qta"), None
            )
            if not col_desc or not col_qta:
                continue

            df = df[[col_desc, col_qta]].copy()
            df = df.rename(columns={col_desc: "Descrizione", col_qta: "Qta"})
            df = df[df["Descrizione"].notna()].copy()
            df = df[df["Descrizione"].astype(str).str.strip() != ""].copy()
            df = df[df["Descrizione"].astype(str).str.strip() != "nan"].copy()

            onglets[desc] = df
            print(f"✅ Onglet {sheet} | Desc.Port: {desc} | {len(df)} lignes")

        except Exception as e:
            print(f"⚠️ Onglet {sheet} ignoré : {e}")

    return onglets


def trouver_onglet(client_pdf, onglets):
    """
    Matcher le nom client PDF avec Desc.Port. d'un onglet.
    ex: "ASB AXION SICAV BANCASTATO - AZIONARIO GLOBALE FUND"
    ↔  "ASB BancaStato Azionario Globale"
    """
    norm_pdf = normaliser(client_pdf)

    best_match = None
    best_score = 0

    for desc, df in onglets.items():
        norm_desc = normaliser(desc)
        tokens_pdf  = set(re.findall(r'[A-Z0-9]{3,}', norm_pdf))
        tokens_desc = set(re.findall(r'[A-Z0-9]{3,}', norm_desc))
        score = len(tokens_pdf & tokens_desc)
        if score > best_score:
            best_score = score
            best_match = desc

    if best_score >= 1:
        return best_match
    return None


def agréger_client(df):
    """Qta > 0 = Long, Qta < 0 = Short"""
    df = df.copy()
    df["Qta"] = pd.to_numeric(df["Qta"], errors="coerce").fillna(0)
    df["Client_Long"]  = df["Qta"].apply(lambda x: x  if x > 0 else 0)
    df["Client_Short"] = df["Qta"].apply(lambda x: -x if x < 0 else 0)
    resume = df.groupby("Descrizione", as_index=False).agg(
        Client_Long  = ("Client_Long",  "sum"),
        Client_Short = ("Client_Short", "sum"),
    )
    return resume


def matcher_produit(product_pdf, df_client):
    """
    Matcher produit PDF avec Descrizione client.
    """
    product_upper = product_pdf.upper().strip()

    # Étape 1 : MAPPING_DIRECT + Mon/Yr
    mc = re.search(
        r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s*(\d{2})',
        product_upper
    )
    mon_pdf = mc.group(1) if mc else ""
    yr_pdf  = mc.group(2) if mc else ""

    for cle_pdf, cle_client in MAPPING_DIRECT.items():
        if cle_pdf.upper() in product_upper:
            for _, row in df_client.iterrows():
                desc = str(row["Descrizione"]).upper()
                if cle_client.upper() in desc:
                    # Vérifier Mon + Yr
                    mc2 = re.search(
                        r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s*(\d{2})',
                        desc
                    )
                    mon_c = mc2.group(1) if mc2 else ""
                    yr_c  = mc2.group(2) if mc2 else ""
                    if mon_pdf == mon_c and yr_pdf == yr_c:
                        return row["Descrizione"]

    # Étape 2 : tokens communs
    norm_pdf = re.sub(
        r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{2}', '',
        normaliser(product_upper)
    )
    best_match = None
    best_score = 0

    for _, row in df_client.iterrows():
        norm_client = re.sub(
            r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{2}', '',
            normaliser(str(row["Descrizione"]))
        )
        tokens_pdf    = set(re.findall(r'[A-Z0-9]{2,}', norm_pdf))
        tokens_client = set(re.findall(r'[A-Z0-9]{2,}', norm_client))
        score = len(tokens_pdf & tokens_client)
        if score > best_score:
            best_score = score
            best_match = row["Descrizione"]

    if best_score >= 2:
        return best_match
    return None


def comparer(df_pdf, onglets, client_pdf):
    """
    Comparer positions PDF vs onglet client correspondant.
    """
    # Trouver l'onglet correspondant
    desc_match = trouver_onglet(client_pdf, onglets)
    if not desc_match:
        print(f"⚠️ Aucun onglet trouvé pour : {client_pdf}")
        df_client = pd.DataFrame(columns=["Descrizione", "Client_Long", "Client_Short"])
    else:
        print(f"✅ Onglet trouvé : {desc_match}")
        df_client = agréger_client(onglets[desc_match])

    resultats = []
    for _, row in df_pdf.iterrows():
        product_pdf = str(row.get("Product", "")).strip()
        long_pdf    = float(row.get("Long",  0) or 0)
        short_pdf   = float(row.get("Short", 0) or 0)

        match = matcher_produit(product_pdf, df_client) if not df_client.empty else None

        if match:
            ligne_client = df_client[df_client["Descrizione"] == match].iloc[0]
            client_long  = float(ligne_client["Client_Long"])
            client_short = float(ligne_client["Client_Short"])

            ecarts = []
            if long_pdf != client_long:
                ecarts.append("ÉCART LONG")
            if short_pdf != client_short:
                ecarts.append("ÉCART SHORT")
            status = ("⚠️ " + " & ".join(ecarts)) if ecarts else "✅ OK"
        else:
            match        = ""
            client_long  = ""
            client_short = ""
            status       = "❌ NON TROUVÉ"

        resultats.append({
            "Product PDF":    product_pdf,
            "Descrizione":    match,
            "Long PDF":       long_pdf  if long_pdf  != 0 else "",
            "Short PDF":      short_pdf if short_pdf != 0 else "",
            "Client Long":    client_long,
            "Client Short":   client_short,
            "Status":         status,
        })

    return pd.DataFrame(resultats)
