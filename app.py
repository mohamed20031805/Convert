import streamlit as st
import tempfile
import os
import pdfplumber
from exporter import exporter_excel
from formats import morgan, triton
from formats_client.morgan_client import charger_client, agréger_client, joindre, extraire_code_client
from formats_client.triton_client import charger_client as charger_client_triton
from formats_client.triton_client import agréger_client as agréger_client_triton
from formats_client.triton_client import joindre as joindre_triton

# ── Formats disponibles ──
FORMATS = [triton, morgan]
TEMPLATES = {
    "morgan": "templates/morgan_stanley.json",
    "triton": "templates/triton.json",
}

def detecter_format(chemin_pdf):
    with pdfplumber.open(chemin_pdf) as pdf:
        texte = pdf.pages[0].extract_text() or ""
    for fmt in FORMATS:
        if fmt.detecter(texte):
            return fmt
    return None

# ── Initialiser session_state ──
for key, val in [
    ("extraction_done", False),
    ("output_df",       None),
    ("entete",          {}),
    ("nom_format",      ""),
    ("fichier_excel",   None),
    ("lignes",          []),
]:
    if key not in st.session_state:
        st.session_state[key] = val

# ── Configuration page ──
st.set_page_config(
    page_title="PDF Extractor - Open Positions",
    page_icon="📊",
    layout="centered"
)

st.title("📊 PDF Extractor — Open Positions")
st.markdown("Extrayez les positions ouvertes de vos PDFs et exportez en Excel.")
st.divider()

# ══════════════════════════════════════════
# 1. Upload PDF
# ══════════════════════════════════════════
st.subheader("1️⃣  Chargez votre PDF")
pdf_file = st.file_uploader("Glissez-déposez votre PDF ici", type=["pdf"])
st.divider()

# ══════════════════════════════════════════
# 2. Extraction
# ══════════════════════════════════════════
st.subheader("2️⃣  Extraction")

if pdf_file is not None:
    if st.button("🚀 Lancer l'extraction", type="primary", use_container_width=True):
        with st.spinner("Extraction en cours..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(pdf_file.read())
                tmp_path = tmp.name
            try:
                fmt = detecter_format(tmp_path)
                if not fmt:
                    st.error("❌ Format PDF non reconnu !")
                else:
                    nom_format = fmt.__name__.split(".")[-1]
                    template   = TEMPLATES.get(nom_format)
                    entete     = fmt.extraire_entete(tmp_path, template)
                    lignes     = fmt.extraire_positions(tmp_path)
                    output_df  = fmt.formater_output(lignes)

                    st.session_state.extraction_done = True
                    st.session_state.output_df       = output_df
                    st.session_state.entete          = entete
                    st.session_state.nom_format      = nom_format
                    st.session_state.lignes          = lignes

                    os.makedirs("output", exist_ok=True)
                    st.session_state.fichier_excel = exporter_excel(output_df, entete, tmp_path)

            except Exception as e:
                st.error(f"❌ Erreur : {e}")
                import traceback
                st.code(traceback.format_exc())
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
else:
    st.info("👆 Chargez un PDF pour commencer")

# ══════════════════════════════════════════
# 3. Résultats
# ══════════════════════════════════════════
if st.session_state.extraction_done:
    entete     = st.session_state.entete
    output_df  = st.session_state.output_df
    nom_format = st.session_state.nom_format

    st.success(f"✅ Extraction terminée ! **{len(st.session_state.lignes)} lignes** extraites.")

    # Infos client
    st.subheader("📋 Informations client")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Broker",  entete.get("Broker",  "—"))
        st.metric("Account", entete.get("Account", "—"))
    with col2:
        st.metric("Client",            entete.get("Client",            "—"))
        st.metric("Close of Business", entete.get("Close of Business", "—"))

    st.divider()

    # Tableau Open Positions
    st.subheader("📊 Open Positions")
    st.dataframe(output_df, use_container_width=True, hide_index=True)

    st.divider()

    # Téléchargement Excel
    st.subheader("3️⃣  Télécharger le fichier Excel")
    fichier_excel = st.session_state.fichier_excel
    if fichier_excel and os.path.exists(fichier_excel):
        with open(fichier_excel, "rb") as f:
            st.download_button(
                label="⬇️ Télécharger le fichier Excel",
                data=f,
                file_name=os.path.basename(fichier_excel),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )

    # ══════════════════════════════════════════
    # 4. Comparaison Doc Client (Morgan uniquement)
    # ══════════════════════════════════════════
if nom_format == "morgan":
        st.divider()
        st.subheader("4️⃣  Comparer avec le Doc Client")
        client_file = st.file_uploader(
            "Chargez le fichier Excel client Morgan",
            type=["xlsx", "xls"],
            key="client_upload"
        )
        if client_file is not None:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_client:
                tmp_client.write(client_file.read())
                tmp_client_path = tmp_client.name
            try:
                df_client_raw = charger_client(tmp_client_path)
                code_client   = extraire_code_client(df_client_raw)

                # ── Extraire le code du PDF (ex: 3757 depuis "STRATEGY - 3757") ──
                import re
                code_pdf = ""
                client_str = entete.get("Client", "")
                m = re.search(r'-\s*(\d+)', client_str)
                if m:
                    code_pdf = m.group(1)

                st.info(f"🔑 Code client détecté : **{code_client}** | Filtre PDF : **{code_pdf}**")

                # ── Filtrer par code PDF ──
                df_client = agréger_client(df_client_raw, code_pdf=code_pdf)

                df_compare = joindre(output_df, df_client)
                st.subheader("📊 Comparaison PDF ↔ Client")
                nb_ok         = len(df_compare[df_compare["Status"] == "✅ OK"])
                nb_ecart      = len(df_compare[df_compare["Status"].str.contains("⚠️", na=False)])
                nb_non_trouve = len(df_compare[df_compare["Status"] == "❌ NON TROUVÉ"])
                col1, col2, col3 = st.columns(3)
                col1.metric("✅ OK",          nb_ok)
                col2.metric("⚠️ Écarts",      nb_ecart)
                col3.metric("❌ Non trouvés", nb_non_trouve)
                def colorer_status(val):
                    if val == "✅ OK":          return "background-color: #d4edda; color: #155724"
                    if "⚠️" in str(val):        return "background-color: #fff3cd; color: #856404"
                    if "❌" in str(val):        return "background-color: #f8d7da; color: #721c24"
                    return ""
                st.dataframe(
                    df_compare.style.applymap(colorer_status, subset=["Status"]),
                    use_container_width=True,
                    hide_index=True
                )
            except Exception as e:
                st.error(f"❌ Erreur fichier client : {e}")
                import traceback
                st.code(traceback.format_exc())
            finally:
                if os.path.exists(tmp_client_path):
                    os.remove(tmp_client_path)
    # ── Section Doc Client Triton ──
    elif nom_format == "triton":
        st.divider()
        st.subheader("4️⃣  Comparer avec le Doc Client Triton")

        client_file = st.file_uploader(
            "Chargez le fichier Excel client Triton",
            type=["xlsx", "xls"],
            key="client_upload_triton"
        )

        if client_file is not None:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_client:
                tmp_client.write(client_file.read())
                tmp_client_path = tmp_client.name

            try:
                df_client_raw = charger_client_triton(tmp_client_path)
                df_client     = agréger_client_triton(df_client_raw)

                df_compare = joindre_triton(output_df, df_client)

                st.subheader("📊 Comparaison PDF ↔ Client Triton")

                nb_ok         = len(df_compare[df_compare["Status"] == "✅ OK"])
                nb_ecart      = len(df_compare[df_compare["Status"].str.contains("⚠️", na=False)])
                nb_non_trouve = len(df_compare[df_compare["Status"] == "❌ NON TROUVÉ"])

                col1, col2, col3 = st.columns(3)
                col1.metric("✅ OK",          nb_ok)
                col2.metric("⚠️ Écarts",      nb_ecart)
                col3.metric("❌ Non trouvés", nb_non_trouve)

                def colorer_status(val):
                    if val == "✅ OK":     return "background-color: #d4edda; color: #155724"
                    if "⚠️" in str(val):  return "background-color: #fff3cd; color: #856404"
                    if "❌" in str(val):  return "background-color: #f8d7da; color: #721c24"
                    return ""

                st.dataframe(
                    df_compare.style.applymap(colorer_status, subset=["Status"]),
                    use_container_width=True,
                    hide_index=True
                )

            except Exception as e:
                st.error(f"❌ Erreur fichier client Triton : {e}")
                import traceback
                st.code(traceback.format_exc())
            finally:
                if os.path.exists(tmp_client_path):

                    os.remove(tmp_client_path)
