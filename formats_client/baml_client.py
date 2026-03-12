import pandas as pd
import re
import json
import os

ACCOUNTS_JSON = "templates/accounts.json"

MAPPING = {
    "EUR-BUND":   ["BUND"],
    "EUR-BOBL":   ["BOBL"],
    "EUR-BTP":    ["BTP"],
    "EURO-BUXL":  ["BUXL"],
    "EURO-BTP":   ["BTP"],
    "E-SCHATZ":   ["SCHATZ"],
    "FOAT":       ["OAT"],
    "ULT TNOTE":  ["ULTRA", "10YR"],
    "10Y TNOTE":  ["10YR", "NOTE"],
    "10Y T-BOND": ["TBOND", "10Y"],
    "T-BOND":     ["TBOND"],
    "EMINI S&P":  ["SP", "EMINI"],
    "EMINI NSDQ": ["NASDAQ", "NSDQ", "EMINI"],
}


def normaliser(texte):
    return re.sub(r'[^A-Z0-9]', '', str(texte).upper())


def charger_accounts():
    if not os.path.exists(ACCOUNTS_JSON):
        return []
    with open(ACCOUNTS_JSON) as f:
        return json.load(f).get("accounts", [])


def lire_nom_client_excel(chemin_excel):
    """Lire ligne 3 du fichier client = nom du fond"""
    df_raw = pd.read_excel(chemin_excel, header=None)
    for i in range(min(6, len(df_raw))):
        row = df_raw.iloc[i]
        valeurs = [str(v).strip() for v in row if pd.notna(v) and str(v).strip()
                   and str(v).strip() != "nan"]
        if valeurs:
            texte = " ".join(valeurs)
            if len(texte) > 10:
                return texte
    return ""


def trouver_account(nom_client_excel):
    """
    Cherche dans accounts.json le compte correspondant au nom du fond.
    Retourne le dict account ou None.
    """
    accounts = charger_accounts()
    norm_excel = normaliser(nom_client_excel)

    best_match = None
    best_score = 0

    for acc in accounts:
        mots  = [normaliser(m) for m in acc["client_name"].split() if len(m) > 2]
        score = sum(1 for m in mots if m in norm_excel)
        if score > best_score:
            best_score = score
            best_match = acc

    # Seuil minimum : au moins la moitié des mots trouvés
    if best_match and best_score >= max(1, len(
        [m for m in best_match["client_name"].split() if len(m) > 2]
    ) // 2):
        return best_match
    return None


def charger_client(chemin_excel):
    """Charger fichier client BAML — header ligne 10"""
    df = pd.read_excel(chemin_excel, header=9)
    df.columns = [str(c).strip() for c in df.columns]
    # Garder seulement lignes avec Security Description
    col_sd = next((c for c in df.columns if "Security" in c and "Desc" in c), None)
    if col_sd and col_sd != "Security Description":
        df = df.rename(columns={col_sd: "Security Description"})
    df = df[df["Security Description"].notna()].copy()
    df = df[df["Security Description"].astype(str).str.strip() != ""].copy()
    return df


def agréger_client(df):
    """Share/Face > 0 = Long, < 0 (parenthèses) = Short"""

    def parse_face(val):
        s = str(val).strip()
        if s.startswith('(') and s.endswith(')'):
            try:
                return -float(s[1:-1].replace(',', ''))
            except:
                return 0.0
        try:
            return float(str(s).replace(',', ''))
        except:
            return 0.0

    df = df.copy()
    col_face = next((c for c in df.columns if "Share" in c or "Face" in c), None)
    col_ccy  = next((c for c in df.columns if "Currency" in c), None)

    if col_face:
        df["_face"] = df[col_face].apply(parse_face)
    else:
        df["_face"] = 0

    df["Client_Long"]  = df["_face"].apply(lambda x: x  if x > 0 else 0)
    df["Client_Short"] = df["_face"].apply(lambda x: -x if x < 0 else 0)

    resume = df.groupby("Security Description", as_index=False).agg(
        Client_Long  = ("Client_Long",  "sum"),
        Client_Short = ("Client_Short", "sum"),
        Currency     = (col_ccy, "first") if col_ccy else ("Client_Long", "first"),
    )
    return resume


def matcher_produit(product_pdf, df_client):
    """
    Matcher product PDF avec Security Description client.
    1. Via MAPPING + Mon/Yr
    2. Fallback : tokens communs
    """
    norm_pdf = normaliser(product_pdf)

    # Étape 1 : MAPPING
    for cle, mots in MAPPING.items():
        if normaliser(cle) in norm_pdf:
            for _, row in df_client.iterrows():
                norm_client = normaliser(row["Security Description"])
                if all(normaliser(m) in norm_client for m in mots):
                    mc = re.search(r'([A-Z]{3})\s*(\d{2})', product_pdf)
                    if mc:
                        mon = mc.group(1)
                        yr  = mc.group(2)
                        if mon in norm_client and yr in norm_client:
                            return row["Security Description"]
                    else:
                        return row["Security Description"]

    # Étape 2 : tokens communs
    tokens_pdf = set(re.findall(r'[A-Z0-9]+', norm_pdf))
    best_match = None
    best_score = 0
    for _, row in df_client.iterrows():
        norm_client   = normaliser(row["Security Description"])
        tokens_client = set(re.findall(r'[A-Z0-9]+', norm_client))
        score = len(tokens_pdf & tokens_client)
        if score > best_score:
            best_score = score
            best_match = row["Security Description"]

    if best_score >= 2:
        return best_match
    return None


def comparer(df_pdf, df_client_raw):
    df_client = agréger_client(df_client_raw)
    resultats = []

    for _, row in df_pdf.iterrows():
        product_pdf = str(row.get("Product", "")).strip()
        long_pdf    = float(row.get("Long",  0) or 0)
        short_pdf   = float(row.get("Short", 0) or 0)

        match = matcher_produit(product_pdf, df_client)

        if match:
            ligne_client = df_client[df_client["Security Description"] == match].iloc[0]
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
            "Product PDF":     product_pdf,
            "Security Client": match,
            "Long PDF":        l
