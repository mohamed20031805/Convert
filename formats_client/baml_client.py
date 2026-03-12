import pandas as pd
import re


# ── Mapping produits PDF → mots-clés client ──
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
    "10Y T-BOND": ["T-BOND", "10Y"],
    "T-BOND":     ["T-BOND"],
    "EMINI S&P":  ["S&P", "EMINI"],
    "EMINI NSDQ": ["NASDAQ", "NSDQ", "EMINI"],
}


def normaliser(texte):
    """Enlever espaces, tirets, points — tout en majuscules"""
    return re.sub(r'[^A-Z0-9]', '', str(texte).upper())


def charger_client(chemin_excel):
    """Charger fichier client BAML — header ligne 10"""
    df = pd.read_excel(chemin_excel, header=9)  # ligne 10 = index 9
    df.columns = [str(c).strip() for c in df.columns]
    # Garder seulement les lignes avec Security Description
    df = df[df["Security Description"].notna()].copy()
    return df


def agréger_client(df):
    """
    Share/Face > 0 → Long
    Share/Face < 0 (parenthèses) → Short
    """
    def parse_face(val):
        s = str(val).strip()
        # Parenthèses = négatif ex: (7.00) → -7.0
        if s.startswith('(') and s.endswith(')'):
            try:
                return -float(s[1:-1].replace(',', ''))
            except:
                return 0.0
        try:
            return float(str(s).replace(',', ''))
        except:
            return 0.0

    df["_face"] = df["Share/Face"].apply(parse_face)
    df["Client_Long"]  = df["_face"].apply(lambda x: x  if x > 0 else 0)
    df["Client_Short"] = df["_face"].apply(lambda x: -x if x < 0 else 0)

    resume = df.groupby("Security Description", as_index=False).agg(
        Client_Long  = ("Client_Long",  "sum"),
        Client_Short = ("Client_Short", "sum"),
        Currency     = ("Currency (Loca", "first"),
    )
    return resume


def matcher_produit(product_pdf, df_client):
    """
    Trouver la ligne client qui correspond au produit PDF.
    Méthode :
    1. Normaliser les 2 côtés
    2. Chercher les mots-clés du mapping
    3. Si pas trouvé → matching flou par tokens
    """
    norm_pdf = normaliser(product_pdf)

    # Étape 1 : via MAPPING
    for cle, mots in MAPPING.items():
        if normaliser(cle) in norm_pdf:
            for _, row in df_client.iterrows():
                norm_client = normaliser(row["Security Description"])
                if all(normaliser(m) in norm_client for m in mots):
                    # Vérifier aussi Mon + Yr
                    mc = re.search(r'([A-Z]{3})\s*(\d{2})', product_pdf)
                    if mc:
                        mon = mc.group(1)[:3]
                        yr  = mc.group(2)
                        if mon in norm_client and yr in norm_client:
                            return row["Security Description"]
                    else:
                        return row["Security Description"]

    # Étape 2 : matching flou par tokens
    tokens_pdf = set(re.findall(r'[A-Z0-9]+', norm_pdf))
    best_match = None
    best_score = 0
    for _, row in df_client.iterrows():
        norm_client = normaliser(row["Security Description"])
        tokens_client = set(re.findall(r'[A-Z0-9]+', norm_client))
        # Score = nb tokens en commun
        communs = tokens_pdf & tokens_client
        score = len(communs)
        if score > best_score:
            best_score = score
            best_match = row["Security Description"]

    # Seuil minimum
    if best_score >= 2:
        return best_match
    return None


def comparer(df_pdf, df_client_raw):
    """
    Comparer positions PDF vs client.
    df_pdf : output de formater_output (lignes brutes)
    """
    df_client = agréger_client(df_client_raw)

    resultats = []
    for _, row in df_pdf.iterrows():
        product_pdf = str(row.get("Product", "")).strip()
        long_pdf    = float(row.get("Long",  0) or 0)
        short_pdf   = float(row.get("Short", 0) or 0)

        # Matcher
        match = matcher_produit(product_pdf, df_client)

        if match:
            ligne_client = df_client[df_client["Security Description"] == match].iloc[0]
            client_long  = float(ligne_client["Client_Long"])
            client_short = float(ligne_client["Client_Short"])

            # Status
            ecarts = []
            if long_pdf != client_long:
                ecarts.append("ÉCART LONG")
            if short_pdf != client_short:
                ecarts.append("ÉCART SHORT")

            if ecarts:
                status = "⚠️ " + " & ".join(ecarts)
            else:
                status = "✅ OK"
        else:
            match        = ""
            client_long  = ""
            client_short = ""
            status       = "❌ NON TROUVÉ"

        resultats.append({
            "Product PDF":      product_pdf,
            "Security Client":  match,
            "Long PDF":         long_pdf  or "",
            "Short PDF":        short_pdf or "",
            "Client Long":      client_long,
            "Client Short":     client_short,
            "Status":           status,
        })

    return pd.DataFrame(resultats)
