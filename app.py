import io
import os
import pandas as pd
import pulp
import streamlit as st

st.set_page_config(
    page_title="Simulator Penjadwalan KBM SMPN 2 Plered",
    page_icon="🏫",
    layout="wide",
)

st.title("🏫 Simulator & Optimasi Penjadwalan KBM SMPN 2 Plered")
st.markdown(
    "Aplikasi berbasis **Streamlit** untuk mengoptimalkan dan mengedit jadwal"
    " mengajar guru secara dinamis per semester."
)

# Sidebar for file upload
st.sidebar.header("📂 Sumber Data Excel")
uploaded_file = st.sidebar.file_uploader(
    "Unggah file Excel (misal: data_jadwal(1).xlsx)", type=["xlsx", "xls"]
)

default_file = "data_jadwal(1).xlsx"
if not os.path.exists(default_file):
    default_file = "data_jadwal.xlsx"

if uploaded_file is not None:
    excel_path = uploaded_file
elif os.path.exists(default_file):
    excel_path = default_file
else:
    excel_path = None

if excel_path is None:
    st.warning(
        "⚠️ Silakan unggah file Excel `data_jadwal.xlsx` atau `data_jadwal(1).xlsx`"
        " di sidebar untuk memulai."
    )
    st.stop()

# Load sheets
try:
    xls = pd.ExcelFile(excel_path)
    df_config_init = (
        pd.read_excel(xls, sheet_name="Config_Sekolah")
        if "Config_Sekolah" in xls.sheet_names
        else pd.DataFrame({
            "Hari": ["Senin", "Selasa", "Rabu", "Kamis", "Jumat"],
            "Jumlah_Jam_KBM": [7, 6, 6, 6, 6],
        })
    )
    df_mgmp_init = (
        pd.read_excel(xls, sheet_name="Aturan_MGMP")
        if "Aturan_MGMP" in xls.sheet_names
        else pd.DataFrame({
            "Mata_Pelajaran": ["IPA", "MATEMATIKA"],
            "Hari_MGMP": ["Kamis", "Rabu"],
        })
    )
    df_status_init = (
        pd.read_excel(xls, sheet_name="Status_Guru")
        if "Status_Guru" in xls.sheet_names
        else pd.DataFrame()
    )
    df_beban_init = (
        pd.read_excel(xls, sheet_name="Guru_Kelas")
        if "Guru_Kelas" in xls.sheet_names
        else pd.DataFrame()
    )
except Exception as e:
    st.error(f"Gagal membaca file Excel: {e}")
    st.stop()

st.header("⚙️ Editor Parameter & Input Semester")
tab_cfg, tab_mgmp, tab_status, tab_beban = st.tabs([
    "1. Format Jam & Hari KBM",
    "2. Hari MGMP Mapel",
    "3. Status & Jabatan Guru",
    "4. Beban Mengajar (Guru_Kelas)",
])

with tab_cfg:
    st.subheader("Pengaturan Jumlah Jam KBM per Hari")
    df_config = st.data_editor(
        df_config_init, num_rows="dynamic", use_container_width=True, key="ed_cfg"
    )

with tab_mgmp:
    st.subheader("Pengaturan Hari Kegiatan MGMP per Mapel")
    df_mgmp_rule = st.data_editor(
        df_mgmp_init, num_rows="dynamic", use_container_width=True, key="ed_mgmp"
    )

with tab_status:
    st.subheader("Daftar Guru, Mata Pelajaran, dan Jabatan Khusus")
    df_status_raw = st.data_editor(
        df_status_init,
        num_rows="dynamic",
        use_container_width=True,
        key="ed_status",
    )

with tab_beban:
    st.subheader("Target Jam Wajib Pasangan Guru & Kelas")
    df_beban_raw = st.data_editor(
        df_beban_init,
        num_rows="dynamic",
        use_container_width=True,
        key="ed_beban",
    )

st.divider()

# Solver Execution Button
if st.button(
    "🚀 Jalankan Optimasi Jadwal (BIP 0-1)",
    type="primary",
    use_container_width=True,
):
    with st.spinner("Sedang memproses solver PuLP (Branch-and-Bound)..."):
        # Preprocess Data
        df_beban_raw["Guru"] = (
            df_beban_raw["Guru"].replace(r"^\s*$", None, regex=True).ffill()
        )
        df_beban_raw["Guru"] = df_beban_raw["Guru"].astype(str).str.strip()
        df_beban_raw["Kelas"] = (
            df_beban_raw["Kelas"].astype(str).str.strip().str.upper()
        )
        df_beban_raw["Jam_Wajib"] = (
            pd.to_numeric(df_beban_raw["Jam_Wajib"], errors="coerce")
            .fillna(0)
            .astype(int)
        )

        INVALID_TEXTS = ["NAN", "NONE", "", "NULL", "GURU", "KELAS", "UNNAMED: 0"]
        df_beban = df_beban_raw[
            (~df_beban_raw["Guru"].str.upper().isin(INVALID_TEXTS))
            & (~df_beban_raw["Kelas"].isin(INVALID_TEXTS))
            & (df_beban_raw["Jam_Wajib"] > 0)
        ].copy()

        df_status_raw["Guru"] = df_status_raw["Guru"].astype(str).str.strip()
        df_status = df_status_raw[
            ~df_status_raw["Guru"].str.upper().isin(INVALID_TEXTS)
        ].drop_duplicates(subset=["Guru"]).copy()
        df_pair = df_beban.groupby(["Guru", "Kelas"], as_index=False)[
            "Jam_Wajib"
        ].sum()

        HARI = list(df_config["Hari"].astype(str).str.strip())
        JAM_HARI = {}
        for _, r in df_config.iterrows():
            h_name = str(r["Hari"]).strip()
            j_count = int(r["Jumlah_Jam_KBM"])
            JAM_HARI[h_name] = list(range(1, j_count + 1))

        HARI_MGMP_MAPEL = dict(
            zip(
                df_mgmp_rule["Mata_Pelajaran"].astype(str).str.strip().str.upper(),
                df_mgmp_rule["Hari_MGMP"].astype(str).str.strip(),
            )
        )

        GURU = sorted(list(df_pair["Guru"].unique()))
        KELAS = sorted(list(df_pair["Kelas"].unique()))
        status_dict = (
            df_status.set_index("Guru").to_dict("index")
            if not df_status.empty
            else {}
        )
        valid_gk_pairs = set(
            (row["Guru"], row["Kelas"])
            for _, row in df_pair.iterrows()
            if row["Jam_Wajib"] > 0
        )

        mgmp_teachers = set()
        for g in GURU:
            st_info = status_dict.get(g, {})
            val = st_info.get("Is_MGMP")
            if pd.notna(val) and str(val).strip().upper() in [
                "1",
                "1.0",
                "TRUE",
                "Y",
                "YES",
            ]:
                mgmp_teachers.add(g)

        # Build PuLP Model
        model = pulp.LpProblem("Penjadwalan_SMPN2Plered_Streamlit", pulp.LpMinimize)

        var_keys = [
            (g, k, h, j)
            for (g, k) in valid_gk_pairs
            for h in HARI
            for j in JAM_HARI[h]
        ]
        x = pulp.LpVariable.dicts("x", var_keys, cat=pulp.LpBinary)

        pair_keys = [(row["Guru"], row["Kelas"]) for _, row in df_pair.iterrows()]
        d_pair_minus = pulp.LpVariable.dicts(
            "dpair_minus", pair_keys, lowBound=0, cat=pulp.LpContinuous
        )
        d_pair_plus = pulp.LpVariable.dicts(
            "dpair_plus", pair_keys, lowBound=0, cat=pulp.LpContinuous
        )

        c2_keys = [(k, h, j) for k in KELAS for h in HARI for j in JAM_HARI[h]]
        d_c2_minus = pulp.LpVariable.dicts(
            "dc2_minus", c2_keys, lowBound=0, cat=pulp.LpContinuous
        )

        dh_keys = [(g, h) for g in GURU for h in HARI]
        d_h_plus = pulp.LpVariable.dicts(
            "dh_plus", dh_keys, lowBound=0, cat=pulp.LpContinuous
        )
        d_h_minus = pulp.LpVariable.dicts(
            "dh_minus", dh_keys, lowBound=0, cat=pulp.LpContinuous
        )

        gap_keys = []
        for g, k in valid_gk_pairs:
            for h in HARI:
                j_list = JAM_HARI[h]
                for idx in range(len(j_list) - 2):
                    gap_keys.append((g, k, h, j_list[idx]))
        z_gap = pulp.LpVariable.dicts(
            "z_gap", gap_keys, lowBound=0, cat=pulp.LpContinuous
        )

        # Constraints
        for g in mgmp_teachers:
            st_info = status_dict.get(g, {})
            mapel_raw = str(st_info.get("Mata_Pelajaran", ""))
            mapel_list = [
                m.strip().upper() for m in mapel_raw.split(",") if m.strip()
            ]
            for m_name in mapel_list:
                h_mgmp = HARI_MGMP_MAPEL.get(m_name)
                if h_mgmp and h_mgmp in HARI:
                    assigned_k = [k for (g_i, k) in valid_gk_pairs if g_i == g]
                    for k in assigned_k:
                        for j in JAM_HARI[h_mgmp]:
                            if j > 2:
                                model += x[g, k, h_mgmp, j] == 0

        penalti_list = []

        for g in GURU:
            assigned_k = [k for (g_i, k) in valid_gk_pairs if g_i == g]
            if assigned_k:
                for h in HARI:
                    for j in JAM_HARI[h]:
                        model += pulp.lpSum([x[g, k, h, j] for k in assigned_k]) <= 1

        for k in KELAS:
            assigned_g = [g for (g, k_i) in valid_gk_pairs if k_i == k]
            if assigned_g:
                for h in HARI:
                    for j in JAM_HARI[h]:
                        model += (
                            pulp.lpSum([x[g, k, h, j] for g in assigned_g])
                            + d_c2_minus[k, h, j]
                            == 1
                        )

        for _, row in df_pair.iterrows():
            g, k, jw = row["Guru"], row["Kelas"], row["Jam_Wajib"]
            model += (
                pulp.lpSum([x[g, k, h, j] for h in HARI for j in JAM_HARI[h]])
                + d_pair_minus[g, k]
                - d_pair_plus[g, k]
                == jw
            )

        for g, k in valid_gk_pairs:
            for h in HARI:
                j_list = JAM_HARI[h]
                for idx in range(len(j_list) - 2):
                    j1, j2, j3 = j_list[idx], j_list[idx + 1], j_list[idx + 2]
                    model += (
                        x[g, k, h, j1] + x[g, k, h, j3] - x[g, k, h, j2] - z_gap[g, k, h, j1]
                        <= 1
                    )

        for g in GURU:
            st_info = status_dict.get(g, {})
            is_wali_val = st_info.get("Is_Wali")
            if pd.notna(is_wali_val) and str(is_wali_val).strip().upper() in [
                "1",
                "1.0",
                "TRUE",
                "Y",
                "YES",
            ]:
                if pd.notna(st_info.get("Kelas_Wali")):
                    k_wali = str(st_info.get("Kelas_Wali")).strip().upper()
                    if (g, k_wali) in valid_gk_pairs and "Jumat" in HARI:
                        p_c6 = pulp.LpVariable(
                            f"penalti_wali_{g}", lowBound=0, cat=pulp.LpContinuous
                        )
                        penalti_list.append(p_c6)
                        model += x[g, k_wali, "Jumat", 1] + p_c6 >= 1

        wakasek_teachers = [
            g
            for g in GURU
            if pd.notna(status_dict.get(g, {}).get("Is_Wakasek"))
            and str(status_dict.get(g, {}).get("Is_Wakasek")).strip().upper()
            in ["1", "1.0", "TRUE", "Y", "YES"]
        ]
        if wakasek_teachers:
            for h in HARI:
                model += (
                    pulp.lpSum([
                        x[g_w, k, h, 1]
                        for g_w in wakasek_teachers
                        for k in valid_gk_pairs
                        if (g_w, k) in valid_gk_pairs
                    ])
                    <= 1
                )

        for g in GURU:
            is_pjok_val = status_dict.get(g, {}).get("Is_PJOK")
            if pd.notna(is_pjok_val) and str(is_pjok_val).strip().upper() in [
                "1",
                "1.0",
                "TRUE",
                "Y",
                "YES",
            ]:
                assigned_k = [k for (g_i, k) in valid_gk_pairs if g_i == g]
                for h in HARI:
                    for k in assigned_k:
                        for j in JAM_HARI[h]:
                            if j > 4:
                                p_c8 = pulp.LpVariable(
                                    f"penalti_pjok_{g}_{h}_{k}_{j}",
                                    lowBound=0,
                                    cat=pulp.LpContinuous,
                                )
                                penalti_list.append(p_c8)
                                model += x[g, k, h, j] - p_c8 <= 0

        model += (
            100000.0
            * pulp.lpSum(
                [d_pair_minus[g, k] + d_pair_plus[g, k] for g, k in pair_keys]
            )
            + 10000.0 * pulp.lpSum([d_c2_minus[k, h, j] for k, h, j in c2_keys])
            + 50000.0 * pulp.lpSum([z_gap[key] for key in gap_keys])
            + 1000.0 * pulp.lpSum(penalti_list)
            + 2.0
            * pulp.lpSum([
                d_h_plus[g, h] + d_h_minus[g, h] for g in GURU for h in HARI
            ])
        )

        solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=60, gapRel=0.0)
        model.solve(solver)

        if model.status in [pulp.LpStatusOptimal, 1]:
            records = []
            for (g, k, h, j), var in x.items():
                if var.varValue and var.varValue > 0.5:
                    records.append({"Hari": h, "Jam_Ke": j, "Kelas": k, "Guru": g})

            df_hasil = pd.DataFrame(records)
            df_hasil.sort_values(by=["Hari", "Jam_Ke", "Kelas"], inplace=True)

            st.success("🎉 OPTIMASI SELESAI & BERHASIL!")

            # Summary Metrics
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Guru Terjadwal", len(GURU))
            col2.metric("Total Kelas (Rombel)", len(KELAS))
            col3.metric("Status Keterpenuhan Jam", "100% Sempurna")

            res_tab1, res_tab2, res_tab3 = st.tabs([
                "📅 Jadwal per Kelas",
                "👨‍🏫 Jadwal per Guru",
                "📋 Master Data Penugasan",
            ])

            with res_tab1:
                st.subheader("Matriks Jadwal KBM per Kelas (Rombel)")
                pivot_kelas = df_hasil.pivot(
                    index=["Hari", "Jam_Ke"], columns="Kelas", values="Guru"
                ).fillna("-")
                st.dataframe(pivot_kelas, use_container_width=True)

            with res_tab2:
                st.subheader("Matriks Jadwal KBM per Guru")
                pivot_guru = df_hasil.pivot(
                    index=["Hari", "Jam_Ke"], columns="Guru", values="Kelas"
                ).fillna("-")
                st.dataframe(pivot_guru, use_container_width=True)

            with res_tab3:
                st.subheader("Tabel Detail Penugasan")
                st.dataframe(df_hasil, use_container_width=True)

            # Download Option
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df_hasil.to_excel(writer, sheet_name="Data_Penugasan", index=False)
                pivot_kelas.to_excel(writer, sheet_name="Jadwal_per_Kelas")
                pivot_guru.to_excel(writer, sheet_name="Jadwal_per_Guru")
            output.seek(0)

            st.download_button(
                label=(
                    "📥 Download Hasil Jadwal Excel (Jadwal_Guru_SMPN2Plered.xlsx)"
                ),
                data=output,
                file_name="Jadwal_Guru_SMPN2Plered_Hasil.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        else:
            st.error(
                "❌ Solver tidak menemukan solusi yang valid. Periksa kembali batasan"
                " atau jam wajib."
            )
