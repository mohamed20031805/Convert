import streamlit as st
import tempfile
import os
import re
import pdfplumber
from exporter import exporter_excel
from formats import morgan, triton, baml
from formats_client.morgan_client import charger_client, agréger_client, joindre, extraire_code_client
from formats_client.triton_client import charger_client as charger_client_triton
from formats_client.triton_client import agréger_client as agréger_client_triton
from formats_client.triton_client import joindre as joindre_triton
import formats_client.baml_client as baml_client

FORMATS = [triton, baml, morgan]
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

for key, val in [
    ("extraction_done", False),
    ("output_df",       None),
    ("entete",          {}),
    ("nom_format",      ""),
    ("fichier_excel",   None),
    ("lignes",          []),
    ("tmp_pdf_bytes",   None),
]:
    if key not in st.session_state:
        st.session_state[key] = val

st.set_page_config(page_title="PDF Extractor - Open Positions", page_icon="📊", layout="centered")
st.title("📊 PDF Extractor — Open Positions")
st.markdown("Extrayez les positions ouvertes de vos PDFs et exportez en Excel.")
st.divider()

# ── 1. Upload PDF ──
st.subheader("1️⃣  Chargez votre PDF")
pdf_file = st.file_uploader("Glissez-déposez votre PDF ici", type=["pdf"])
st.divider()

# ── 2. Extraction ──
st.subheader("2️⃣  Extraction")

if pdf_file is not None:
    # Sauvegarder bytes pour réutilisation
    st.session_state.tmp_pdf_bytes = pdf_file.read()
    pdf_file.seek(0)

    if st.button("🚀 Lancer l'extraction", type="primary", use_container_width=True):
        with st.spinner("Extraction en cours..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(st.session_state.tmp_pdf_bytes)
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

# ── 3. Résultats ──
if st.session_state.extraction_done:
    entete     = st.session_state.entete
    output_df  = st.session_state.output_df
    nom_format = st.session_state.nom_format

    st.success(f"✅ Extraction terminée ! **{len(st.session_state.lignes)} lignes** extraites.")

    st.subheader("📋 Informations client")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Broker",  entete.get("Broker",  "—"))
        st.metric("Account", entete.get("Account", "—"))
    with col2:
        st.metric("Client",            entete.get("Client",            "—"))
        st.metric("Close of Business", entete.get("Close of Business", "—"))

    st.divider()
    st.subheader("📊 Open Positions")
    st.dataframe(output_df, use_container_width=True, hide_index=True)
    st.divider()

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

    st.divider()

    def afficher_comparaison(df_compare):
        nb_ok         = len(df_compare[df_compare["Status"] == "✅ OK"])
        nb_ecart      = len(df_compare[df_compare["Status"].str.contains("⚠️", na=False)])
        nb_non_trouve = len(df_compare[df_compare["Status"] == "❌ NON TROUVÉ"])
        col1, col2, col3 = st.columns(3)
        col1.metric("✅ OK",          nb_ok)
        col2.metric("⚠️ Écarts",      nb_ecart)
        col3.metric("❌ Non trouvés", nb_non_trouve)

        def colorer_status(val):
            if val == "✅ OK":       return "background-color: #d4edda; color: #155724"
            if "⚠️" in str(val):    return "background-color: #fff3cd; color: #856404"
            if "❌" in str(val):    return "background-color: #f8d7da; color: #721c24"
            return ""

        st.dataframe(
            df_compare.style.applymap(colorer_status, subset=["Status"]),
            use_container_width=True,
            hide_index=True
        )

    # ── Morgan ──
    if nom_format == "morgan":
        st.subheader("4️⃣  Comparer avec le Doc Client Morgan")
        client_file = st.file_uploader("Chargez le fichier Excel client Morgan",
                                        type=["xlsx","xls"], key="client_upload")
        if client_file:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_c:
                tmp_c.write(client_file.read())
                tmp_c_path = tmp_c.name
            try:
                df_client_raw = charger_client(tmp_c_path)
                code_client   = extraire_code_client(df_client_raw)
                code_pdf = ""
                m = re.search(r'-\s*(\d+)', entete.get("Client", ""))
                if m:
                    code_pdf = m.group(1)
                st.info(f"🔑 Code client : **{code_client}** | Filtre PDF : **{code_pdf}**")
                df_client  = agréger_client(df_client_raw, code_pdf=code_pdf)
                df_compare = joindre(output_df, df_client)
                st.subheader("📊 Comparaison PDF ↔ Client Morgan")
                afficher_comparaison(df_compare)
            except Exception as e:
                st.error(f"❌ Erreur : {e}")
                import traceback; st.code(traceback.format_exc())
            finally:
                if os.path.exists(tmp_c_path): os.remove(tmp_c_path)

    # ── Triton ──
    elif nom_format == "triton":
        st.subheader("4️⃣  Comparer avec le Doc Client Triton")
        client_file = st.file_uploader("Chargez le fichier Excel client Triton",
                                        type=["xlsx","xls"], key="client_upload_triton")
        if client_file:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_c:
                tmp_c.write(client_file.read())
                tmp_c_path = tmp_c.name
            try:
                df_client_raw = charger_client_triton(tmp_c_path)
                df_client     = agréger_client_triton(df_client_raw)
                df_compare    = joindre_triton(output_df, df_client)
                st.subheader("📊 Comparaison PDF ↔ Client Triton")
                afficher_comparaison(df_compare)
            except Exception as e:
                st.error(f"❌ Erreur : {e}")
                import traceback; st.code(traceback.format_exc())
            finally:
                if os.path.exists(tmp_c_path): os.remove(tmp_c_path)

    # ── BAML ──
    elif nom_format == "baml":
        st.subheader("4️⃣  Comparer avec le Doc Client BAML")
        client_file = st.file_uploader("Chargez le fichier Excel client BAML",
                                        type=["xlsx","xls"], key="client_upload_baml")
        if client_file:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_c:
                tmp_c.write(client_file.read())
                tmp_c_path = tmp_c.name
            try:
                # ── Détecter compte depuis ligne 3 du fichier client ──
                nom_fond = baml_client.lire_nom_client_excel(tmp_c_path)
                account  = baml_client.trouver_account(nom_fond)

                if account:
                    account_number = account["account_number"]
                    st.info(f"🔑 Compte détecté : **{account_number}** — {account['client_name']}")
                else:
                    account_number = None
                    st.warning("⚠️ Compte non trouvé dans accounts.json — toutes les pages extraites")

                # ── Ré-extraire PDF filtré par compte ──
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                    tmp_pdf.write(st.session_state.tmp_pdf_bytes)
                    tmp_pdf_path = tmp_pdf.name

                lignes_filtrees  = baml.extraire_positions(tmp_pdf_path, account_number=account_number)
                output_df_filtre = baml.formater_output(lignes_filtrees)

                st.info(f"📄 **{len(lignes_filtrees)} positions** pour ce compte")
                st.dataframe(output_df_filtre, use_container_width=True, hide_index=True)

                # ── Comparaison ──
                df_client_raw = baml_client.charger_client(tmp_c_path)
                df_compare    = baml_client.comparer(output_df_filtre, df_client_raw)

                st.subheader("📊 Comparaison PDF ↔ Client BAML")
                afficher_comparaison(df_compare)

            except Exception as e:
                st.error(f"❌ Erreur : {e}")
                import traceback; st.code(traceback.format_exc())
            finally:
                if os.path.exists(tmp_c_path):  os.remove(tmp_c_path)
                if os.path.exists(tmp_pdf_path): os.remove(tmp_pdf_path)
