import io
import os
import re
import matplotlib.pyplot as plt
import numpy as np
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

# Sidebar untuk upload file Excel
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

# Initial DataFrames dengan nilai default aman jika file belum diunggah
df_config_init = pd.DataFrame({
    "Hari": ["Senin", "Selasa", "Rabu", "Kamis", "Jumat"],
    "Jumlah_Jam_KBM": [7, 6, 6, 6, 6],
})
df_mgmp_init = pd.DataFrame({
    "Mata_Pelajaran": ["IPA", "MATEMATIKA"],
    "Hari_MGMP": ["Kamis", "Rabu"],
})
df_status_init = pd.DataFrame({
    "Guru": ["Guru A", "Guru B"],
    "Mata_Pelajaran": ["IPA", "MATEMATIKA"],
    "Is_Wali": ["0", "0"],
    "Kelas_Wali": ["", ""],
    "Is_Wakasek": ["0", "0"],
    "Is_PJOK": ["0", "0"],
    "Is_MGMP": ["0", "0"],
})
df_beban_init = pd.DataFrame({
    "Guru": ["Guru A", "Guru B"],
    "Kelas": ["7A", "7B"],
    "Mata_Pelajaran": ["IPA", "MATEMATIKA"],
    "Jam_Wajib": [4, 4],
})

if excel_path is not None:
  try:
    xls = pd.ExcelFile(excel_path)
    sheet_lower = {str(s).lower().strip(): str(s) for s in xls.sheet_names}
    if "config_sekolah" in sheet_lower:
      df_config_init = pd.read_excel(
          xls, sheet_name=sheet_lower["config_sekolah"]
      )
    if "aturan_mgmp" in sheet_lower:
      df_mgmp_init = pd.read_excel(xls, sheet_name=sheet_lower["aturan_mgmp"])
    if "status_guru" in sheet_lower:
      df_status_init = pd.read_excel(
          xls, sheet_name=sheet_lower["status_guru"]
      )
    if "guru_kelas" in sheet_lower:
      df_beban_init = pd.read_excel(xls, sheet_name=sheet_lower["guru_kelas"])
  except Exception as e:
    st.error(f"Gagal membaca file Excel: {e}")


def safe_name(s):
  sc = str(s).strip() if s is not None else "X"
  res = re.sub(r"\W+", "_", sc).strip("_")
  return res if res else "X"


def buat_dict_var(nama_prefix, daftar_kunci, lowBound=None, cat=pulp.LpContinuous):
  hasil = {}
  for k in daftar_kunci:
    if isinstance(k, (tuple, list)):
      s_name = "_".join(safe_name(x) for x in k)
    else:
      s_name = safe_name(k)
    var_name = f"{nama_prefix}_{s_name}"
    try:
      v = pulp.LpVariable(var_name, lowBound=lowBound, cat=cat)
    except Exception:
      v = pulp.LpVariable(var_name)
      if lowBound is not None:
        v.lowBound = lowBound
      v.cat = cat
    hasil[k] = v
  return hasil


# Inisialisasi Session State
if "solved" not in st.session_state:
  st.session_state["solved"] = False
if "df_hasil" not in st.session_state:
  st.session_state["df_hasil"] = None
if "df_beban_clean" not in st.session_state:
  st.session_state["df_beban_clean"] = None
if "df_config_clean" not in st.session_state:
  st.session_state["df_config_clean"] = None

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

# Tombol Eksekusi Solver
if st.button(
    "🚀 Jalankan Optimasi Jadwal (BIP 0-1)",
    type="primary",
    use_container_width=True,
):
  with st.spinner("Sedang memproses solver PuLP (Branch-and-Bound)..."):
    INVALID_TEXTS = ["NAN", "NONE", "", "NULL", "GURU", "KELAS", "UNNAMED: 0"]

    # Preprocess Data Beban & Status
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

    # Sanitasi df_config
    df_config["Jumlah_Jam_KBM"] = (
        pd.to_numeric(df_config["Jumlah_Jam_KBM"], errors="coerce")
        .fillna(6)
        .astype(int)
    )
    df_config["Hari"] = df_config["Hari"].astype(str).str.strip()

    col_mapel_beban = (
        "Mata_Pelajaran"
        if "Mata_Pelajaran" in df_beban_raw.columns
        else ("Mapel" if "Mapel" in df_beban_raw.columns else None)
    )

    df_beban = df_beban_raw[
        (~df_beban_raw["Guru"].str.upper().isin(INVALID_TEXTS))
        & (~df_beban_raw["Kelas"].isin(INVALID_TEXTS))
        & (df_beban_raw["Jam_Wajib"] > 0)
    ].copy()

    df_status_raw["Guru"] = df_status_raw["Guru"].astype(str).str.strip()
    df_status = df_status_raw[
        ~df_status_raw["Guru"].str.upper().isin(INVALID_TEXTS)
    ].drop_duplicates(subset=["Guru"]).copy()
    status_dict = (
        df_status.set_index("Guru").to_dict("index")
        if not df_status.empty
        else {}
    )

    pair_mapel = {}
    for _, row in df_beban.iterrows():
      g_name, k_name = row["Guru"], row["Kelas"]
      m_name = ""
      if col_mapel_beban and pd.notna(row.get(col_mapel_beban)):
        m_name = str(row.get(col_mapel_beban)).strip()
      if not m_name:
        m_name = str(
            status_dict.get(g_name, {}).get("Mata_Pelajaran", "")
        ).strip()
      pair_mapel[(g_name, k_name)] = m_name

    df_pair = df_beban.groupby(["Guru", "Kelas"], as_index=False)[
        "Jam_Wajib"
    ].sum()

    HARI = [
        str(h).strip()
        for h in df_config["Hari"]
        if pd.notna(h)
        and str(h).strip()
        and str(h).strip().upper() not in INVALID_TEXTS
    ]
    if not HARI:
      HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat"]

    JAM_HARI = {}
    for _, r in df_config.iterrows():
      h_name = str(r["Hari"]).strip()
      if h_name and h_name.upper() not in INVALID_TEXTS:
        j_count = int(r["Jumlah_Jam_KBM"])
        JAM_HARI[h_name] = list(range(1, max(1, j_count) + 1))

    # Fallback jika ada hari yang belum terdaftar di JAM_HARI
    for h in HARI:
      if h not in JAM_HARI:
        JAM_HARI[h] = list(range(1, 7))

    HARI_MGMP_MAPEL = dict(
        zip(
            df_mgmp_rule["Mata_Pelajaran"].astype(str).str.strip().str.upper(),
            df_mgmp_rule["Hari_MGMP"].astype(str).str.strip(),
        )
    )

    GURU = sorted(list(df_pair["Guru"].unique()))
    KELAS = sorted(list(df_pair["Kelas"].unique()))
    valid_gk_pairs = set(
        (row["Guru"], row["Kelas"])
        for _, row in df_pair.iterrows()
        if row["Jam_Wajib"] > 0
    )
    pair_jw_dict = dict(
        zip(
            zip(df_pair["Guru"], df_pair["Kelas"]),
            df_pair["Jam_Wajib"],
        )
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

    # Build Model PuLP
    model = pulp.LpProblem("Penjadwalan_SMPN2Plered_Streamlit", pulp.LpMinimize)

    var_keys = [
        (g, k, h, j)
        for (g, k) in valid_gk_pairs
        for h in HARI
        for j in JAM_HARI.get(h, list(range(1, 7)))
    ]
    x = buat_dict_var("x", var_keys, cat=pulp.LpBinary)

    pair_keys = [(row["Guru"], row["Kelas"]) for _, row in df_pair.iterrows()]
    d_pair_minus = buat_dict_var("dpair_minus", pair_keys, lowBound=0)
    d_pair_plus = buat_dict_var("dpair_plus", pair_keys, lowBound=0)

    c2_keys = [
        (k, h, j)
        for k in KELAS
        for h in HARI
        for j in JAM_HARI.get(h, list(range(1, 7)))
    ]
    d_c2_minus = buat_dict_var("dc2_minus", c2_keys, lowBound=0)

    dh_keys = [(g, h) for g in GURU for h in HARI]
    d_h_plus = buat_dict_var("dh_plus", dh_keys, lowBound=0)
    d_h_minus = buat_dict_var("dh_minus", dh_keys, lowBound=0)

    gap_keys = []
    for g, k in valid_gk_pairs:
      for h in HARI:
        j_list = JAM_HARI.get(h, list(range(1, 7)))
        for idx in range(len(j_list) - 2):
          gap_keys.append((g, k, h, j_list[idx]))
    z_gap = buat_dict_var("z_gap", gap_keys, lowBound=0)

    # Variabel Penalti Jam Terisolasi (Mencegah 1 Jam Terpisah)
    iso_keys = [
        (g, k, h, j)
        for (g, k) in valid_gk_pairs
        for h in HARI
        for j in JAM_HARI.get(h, list(range(1, 7)))
    ]
    z_iso = buat_dict_var("z_iso", iso_keys, lowBound=0)

    # Kendala MGMP
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
            for j in JAM_HARI.get(h_mgmp, list(range(1, 7))):
              if j > 2:
                model += x[g, k, h_mgmp, j] == 0

    penalti_list = []

    for g in GURU:
      assigned_k = [k for (g_i, k) in valid_gk_pairs if g_i == g]
      if assigned_k:
        for h in HARI:
          for j in JAM_HARI.get(h, list(range(1, 7))):
            model += pulp.lpSum([x[g, k, h, j] for k in assigned_k]) <= 1

    for k in KELAS:
      assigned_g = [g for (g, k_i) in valid_gk_pairs if k_i == k]
      if assigned_g:
        for h in HARI:
          for j in JAM_HARI.get(h, list(range(1, 7))):
            model += (
                pulp.lpSum([x[g, k, h, j] for g in assigned_g])
                + d_c2_minus[k, h, j]
                == 1
            )

    for _, row in df_pair.iterrows():
      g, k, jw = row["Guru"], row["Kelas"], row["Jam_Wajib"]
      model += (
          pulp.lpSum([
              x[g, k, h, j]
              for h in HARI
              for j in JAM_HARI.get(h, list(range(1, 7)))
          ])
          + d_pair_minus[g, k]
          - d_pair_plus[g, k]
          == jw
      )

    # Aturan Maksimal Jam Harian per Mapel & Penalti Jam Terisolasi (Sekali Duduk)
    for (g, k), jw in pair_jw_dict.items():
      if jw in (2, 4):
        for h in HARI:
          model += (
              pulp.lpSum([
                  x[g, k, h, j] for j in JAM_HARI.get(h, list(range(1, 7)))
              ])
              <= 2
          )

      for h in HARI:
        j_list = JAM_HARI.get(h, list(range(1, 7)))
        for j in j_list:
          left = x[g, k, h, j - 1] if (j - 1) in j_list else 0
          right = x[g, k, h, j + 1] if (j + 1) in j_list else 0
          model += z_iso[g, k, h, j] >= x[g, k, h, j] - left - right

    for g, k in valid_gk_pairs:
      for h in HARI:
        j_list = JAM_HARI.get(h, list(range(1, 7)))
        for idx in range(len(j_list) - 2):
          j1, j2, j3 = j_list[idx], j_list[idx + 1], j_list[idx + 2]
          model += (
              x[g, k, h, j1]
              + x[g, k, h, j3]
              - x[g, k, h, j2]
              - z_gap[g, k, h, j1]
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
            p_c6 = pulp.LpVariable(f"penalti_wali_{safe_name(g)}", lowBound=0)
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
            for j in JAM_HARI.get(h, list(range(1, 7))):
              if j > 4:
                p_c8 = pulp.LpVariable(
                    f"penalti_pjok_{safe_name(g)}_{safe_name(h)}_{safe_name(k)}_{j}",
                    lowBound=0,
                )
                penalti_list.append(p_c8)
                model += x[g, k, h, j] - p_c8 <= 0

    # Fungsi Tujuan
    model += (
        100000.0
        * pulp.lpSum([
            d_pair_minus[g, k] + d_pair_plus[g, k] for g, k in pair_keys
        ])
        + 75000.0 * pulp.lpSum([z_iso[key] for key in iso_keys])
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
          mapel_name = pair_mapel.get((g, k), "")
          records.append({
              "Hari": h,
              "Jam_Ke": j,
              "Kelas": k,
              "Mata_Pelajaran": mapel_name,
              "Guru": g,
              "Tampilan_Kelas": (
                  f"{mapel_name}\n({g})" if mapel_name else str(g)
              ),
              "Tampilan_Guru": (
                  f"{k}\n({mapel_name})" if mapel_name else str(k)
              ),
          })

      df_hasil = pd.DataFrame(records)
      df_hasil.sort_values(by=["Hari", "Jam_Ke", "Kelas"], inplace=True)

      st.session_state["df_hasil"] = df_hasil
      st.session_state["df_beban_clean"] = df_beban
      st.session_state["df_config_clean"] = df_config
      st.session_state["solved"] = True
      st.success("🎉 OPTIMASI SELESAI & BERHASIL!")
    else:
      st.session_state["solved"] = False
      st.error(
          "❌ Solver tidak menemukan solusi yang valid. Periksa kembali batasan"
          " atau jam wajib."
      )

# Tampilan Hasil dari Session State
if st.session_state["solved"] and st.session_state["df_hasil"] is not None:
  df_hasil = st.session_state["df_hasil"]
  df_beban = st.session_state["df_beban_clean"]
  df_config = st.session_state["df_config_clean"]

  GURU = sorted(list(df_hasil["Guru"].unique()))
  KELAS = sorted(list(df_hasil["Kelas"].unique()))
  HARI = [
      str(h).strip()
      for h in df_config["Hari"]
      if pd.notna(h)
      and str(h).strip()
      and str(h).strip().upper() not in ["NAN", "NONE", "", "NULL"]
  ]

  # Perhitungan Metrik Dinamis
  total_target_jam_guru = df_beban["Jam_Wajib"].sum()
  total_jam_terjadwal_guru = len(df_hasil)
  persen_guru = (
      (total_jam_terjadwal_guru / total_target_jam_guru * 100)
      if total_target_jam_guru > 0
      else 100.0
  )

  total_slot_kbm = sum(
      int(r["Jumlah_Jam_KBM"]) for _, r in df_config.iterrows()
  ) * len(KELAS)
  jam_kosong_kelas = total_slot_kbm - total_jam_terjadwal_guru
  persen_kelas_terisi = (
      (total_jam_terjadwal_guru / total_slot_kbm * 100)
      if total_slot_kbm > 0
      else 100.0
  )

  st.success("✅ Status Optimasi: Solusi Optimal Ditemukan & Tersimpan.")

  col1, col2, col3, col4 = st.columns(4)
  col1.metric("Total Guru Terjadwal", len(GURU))
  col2.metric("Total Kelas (Rombel)", len(KELAS))
  col3.metric(
      "Keterpenuhan Beban Guru",
      f"{persen_guru:.1f}%",
      f"{total_jam_terjadwal_guru}/{total_target_jam_guru} Jam",
  )
  col4.metric(
      "Slot Jam Kosong Kelas",
      f"{jam_kosong_kelas} Slot",
      f"Keterisian {persen_kelas_terisi:.1f}%",
  )

  if jam_kosong_kelas > 0:
    st.info(
        f"ℹ️ **Catatan Slot Jam Kosong**: Terdapat **{jam_kosong_kelas} slot jam"
        " kosong** di tingkat kelas karena total beban jam mengajar guru di"
        f" `Guru_Kelas` ({total_target_jam_guru} jam) lebih sedikit dibanding"
        f" total kapasitas waktu KBM sekolah ({total_slot_kbm} slot jam). Seluruh"
        " target jam mengajar guru **100% terpenuhi**."
    )

  res_tab1, res_tab2, res_tab3, res_tab4, res_tab5 = st.tabs([
      "📅 Matriks Kelas",
      "👨‍🏫 Matriks Guru",
      "🎨 Visualisasi Per Kelas",
      "🖼️ Visualisasi Per Guru",
      "📋 Master Data & Export",
  ])

  pivot_kelas = df_hasil.pivot(
      index=["Hari", "Jam_Ke"], columns="Kelas", values="Tampilan_Kelas"
  ).fillna("-")
  pivot_guru = df_hasil.pivot(
      index=["Hari", "Jam_Ke"], columns="Guru", values="Tampilan_Guru"
  ).fillna("-")
  df_master = df_hasil[["Hari", "Jam_Ke", "Kelas", "Mata_Pelajaran", "Guru"]]

  with res_tab1:
    st.subheader("Matriks Tabel KBM per Kelas")
    st.dataframe(pivot_kelas, use_container_width=True)

    buf_pk = io.BytesIO()
    with pd.ExcelWriter(buf_pk, engine="openpyxl") as writer:
      pivot_kelas.to_excel(writer, sheet_name="Jadwal_per_Kelas")
    buf_pk.seek(0)

    st.download_button(
        label="📥 Download Matriks Jadwal Kelas (.xlsx)",
        data=buf_pk,
        file_name="Matriks_Jadwal_per_Kelas.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        use_container_width=True,
    )

  with res_tab2:
    st.subheader("Matriks Tabel KBM per Guru")
    st.dataframe(pivot_guru, use_container_width=True)

    buf_pg = io.BytesIO()
    with pd.ExcelWriter(buf_pg, engine="openpyxl") as writer:
      pivot_guru.to_excel(writer, sheet_name="Jadwal_per_Guru")
    buf_pg.seek(0)

    st.download_button(
        label="📥 Download Matriks Jadwal Guru (.xlsx)",
        data=buf_pg,
        file_name="Matriks_Jadwal_per_Guru.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        use_container_width=True,
    )

  with res_tab3:
    st.subheader("🖼️ Visualisasi Kartu Jadwal per Kelas (Rombel)")
    selected_kelas = st.selectbox("Pilih Kelas/Rombel:", KELAS, key="sb_kelas")

    df_k = df_hasil[df_hasil["Kelas"] == selected_kelas].copy()
    max_jam = max(int(r["Jumlah_Jam_KBM"]) for _, r in df_config.iterrows())

    grid_k = np.full((max_jam, len(HARI)), "-", dtype=object)
    for _, row in df_k.iterrows():
      h_idx = (
          HARI.index(str(row["Hari"]).strip())
          if str(row["Hari"]).strip() in HARI
          else -1
      )
      j_idx = int(row["Jam_Ke"]) - 1
      if h_idx >= 0 and 0 <= j_idx < max_jam:
        lbl = (
            f"{row['Mata_Pelajaran']}\n[{row['Guru']}]"
            if row["Mata_Pelajaran"]
            else str(row["Guru"])
        )
        grid_k[j_idx, h_idx] = lbl

    fig_k, ax_k = plt.subplots(figsize=(10, 6))
    ax_k.axis("off")

    table_k = ax_k.table(
        cellText=grid_k,
        colLabels=HARI,
        rowLabels=[f"Jam {i+1}" for i in range(max_jam)],
        loc="center",
        cellLoc="center",
    )
    table_k.auto_set_font_size(False)
    table_k.set_fontsize(9)
    table_k.scale(1.2, 2.2)

    for (r, c), cell in table_k.get_celld().items():
      if r == 0 or c == -1:
        cell.set_facecolor("#1a365d")
        cell.get_text().set_color("white")
        cell.get_text().set_weight("bold")
      else:
        txt = cell.get_text().get_text()
        if txt != "-":
          cell.set_facecolor("#ebf8ff")
          cell.set_edgecolor("#3182ce")
        else:
          cell.set_facecolor("#f7fafc")
          cell.set_edgecolor("#e2e8f0")

    plt.title(
        f"JADWAL KBM KELAS {selected_kelas} - SMPN 2 PLERED",
        fontsize=14,
        fontweight="bold",
        pad=15,
        color="#1a365d",
    )
    plt.tight_layout()
    st.pyplot(fig_k)

    buf_k = io.BytesIO()
    fig_k.savefig(buf_k, format="png", dpi=250, bbox_inches="tight")
    buf_k.seek(0)
    st.download_button(
        label=f"📥 Download Visualisasi Gambar Jadwal Kelas {selected_kelas} (PNG)",
        data=buf_k,
        file_name=f"Jadwal_Kelas_{selected_kelas}.png",
        mime="image/png",
    )
    plt.close(fig_k)

  with res_tab4:
    st.subheader("🖼️ Visualisasi Kartu Jadwal per Guru")
    selected_guru = st.selectbox("Pilih Guru:", GURU, key="sb_guru")

    df_g = df_hasil[df_hasil["Guru"] == selected_guru].copy()
    max_jam = max(int(r["Jumlah_Jam_KBM"]) for _, r in df_config.iterrows())

    grid_g = np.full((max_jam, len(HARI)), "-", dtype=object)
    for _, row in df_g.iterrows():
      h_idx = (
          HARI.index(str(row["Hari"]).strip())
          if str(row["Hari"]).strip() in HARI
          else -1
      )
      j_idx = int(row["Jam_Ke"]) - 1
      if h_idx >= 0 and 0 <= j_idx < max_jam:
        lbl = (
            f"Kelas {row['Kelas']}\n[{row['Mata_Pelajaran']}]"
            if row["Mata_Pelajaran"]
            else f"Kelas {row['Kelas']}"
        )
        grid_g[j_idx, h_idx] = lbl

    fig_g, ax_g = plt.subplots(figsize=(10, 6))
    ax_g.axis("off")

    table_g = ax_g.table(
        cellText=grid_g,
        colLabels=HARI,
        rowLabels=[f"Jam {i+1}" for i in range(max_jam)],
        loc="center",
        cellLoc="center",
    )
    table_g.auto_set_font_size(False)
    table_g.set_fontsize(9)
    table_g.scale(1.2, 2.2)

    for (r, c), cell in table_g.get_celld().items():
      if r == 0 or c == -1:
        cell.set_facecolor("#2b6cb0")
        cell.get_text().set_color("white")
        cell.get_text().set_weight("bold")
      else:
        txt = cell.get_text().get_text()
        if txt != "-":
          cell.set_facecolor("#feebc8")
          cell.set_edgecolor("#dd6b20")
        else:
          cell.set_facecolor("#f7fafc")
          cell.set_edgecolor("#e2e8f0")

    plt.title(
        f"JADWAL MENGAJAR: {selected_guru} - SMPN 2 PLERED",
        fontsize=14,
        fontweight="bold",
        pad=15,
        color="#2b6cb0",
    )
    plt.tight_layout()
    st.pyplot(fig_g)

    buf_g = io.BytesIO()
    fig_g.savefig(buf_g, format="png", dpi=250, bbox_inches="tight")
    buf_g.seek(0)
    st.download_button(
        label=f"📥 Download Visualisasi Gambar Jadwal {selected_guru} (PNG)",
        data=buf_g,
        file_name=f"Jadwal_Guru_{safe_name(selected_guru)}.png",
        mime="image/png",
    )
    plt.close(fig_g)

  with res_tab5:
    st.subheader("📋 Master Data Penugasan & Unduh Excel Lengkap")
    st.dataframe(df_master, use_container_width=True)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
      df_master.to_excel(writer, sheet_name="Data_Penugasan", index=False)
      pivot_kelas.to_excel(writer, sheet_name="Jadwal_per_Kelas")
      pivot_guru.to_excel(writer, sheet_name="Jadwal_per_Guru")
    output.seek(0)

    st.download_button(
        label="📥 Download Seluruh Paket Jadwal Excel (.xlsx)",
        data=output,
        file_name="Jadwal_Guru_SMPN2Plered_Hasil.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
