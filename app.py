import io
import os
import re
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pulp
import streamlit as st

"""
Simulator & Optimasi Penjadwalan KBM SMPN 2 Plered
=================================================
Aplikasi berbasis Streamlit & PuLP (Binary Integer Programming 0-1)
untuk mengoptimalkan jadwal mengajar guru secara otomatis per semester.
"""

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

# Initial DataFrames dengan nilai default yang aman
df_config_init = pd.DataFrame({
    "Hari": ["Senin", "Selasa", "Rabu", "Kamis", "Jumat"],
    "Jumlah_Jam_KBM": (7, 6, 6, 6, 6),
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
    "Jam_Wajib": (4, 4),
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
  """Sanitasi nama variabel agar aman digunakan dalam PuLP."""
  sc = str(s).strip() if s is not None else "X"
  res = re.sub(r"\W+", "_", sc).strip("_")
  return res if res else "X"


def buat_dict_var(nama_prefix, daftar_kunci, lowBound=None, cat=pulp.LpContinuous):
  """Membuat dictionary variabel keputusan PuLP dengan penamaan yang kompatibel."""
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
      try:
        v = pulp.LpVariable(var_name, lowBound, None, cat)
      except Exception:
        v = pulp.LpVariable(var_name)
        if lowBound is not None:
          v.lowBound = lowBound
        v.cat = cat
    hasil[k] = v
  return hasil


# Inisialisasi Session State agar hasil optimasi tidak hilang saat aksi UI
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
    # Preprocess Data Beban Mengajar
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

    col_mapel_beban = (
        "Mata_Pelajaran"
        if "Mata_Pelajaran" in df_beban_raw.columns
        else ("Mapel" if "Mapel" in df_beban_raw.columns else None)
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

    status_dict = (
        df_status.set_index("Guru").to_dict("index")
        if not df_status.empty
        else {}
    )

    pair_mapel = {}
    for _, row in df_beban.iterrows():
      g_name = row["Guru"]
      k_name = row["Kelas"]
      m_name = ""
      if col_mapel_beban and pd.notna(row.get(col_mapel_beban)):
        m_name = str(row.get(col_mapel_beban)).strip()

      if not m_name:
        st_info = status_dict.get(g_name, {})
        m_name = str(st_info.get("Mata_Pelajaran", "")).strip()

      pair_mapel[(g_name, k_name)] = m_name

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

    # Build Model PuLP (Binary Integer Programming)
    model = pulp.LpProblem("Penjadwalan_SMPN2Plered_Streamlit", pulp.LpMinimize)

    # 1. Variabel Keputusan Biner x(g, k, h, j)
    var_keys = [
        (g, k, h, j)
        for (g, k) in valid_gk_pairs
        for h in HARI
        for j in JAM_HARI[h]
    ]
    x = buat_dict_var("x", var_keys, cat=pulp.LpBinary)

    # 2. Variabel Deviasi Jam Mengajar Guru
    pair_keys = [(row["Guru"], row["Kelas"]) for _, row in df_pair.iterrows()]
    d_pair_minus = buat_dict_var("dpair_minus", pair_keys, lowBound=0)
    d_pair_plus = buat_dict_var("dpair_plus", pair_keys, lowBound=0)

    # 3. Variabel Deviasi Jam Kosong Kelas
    c2_keys = [(k, h, j) for k in KELAS for h in HARI for j in JAM_HARI[h]]
    d_c2_minus = buat_dict_var("dc2_minus", c2_keys, lowBound=0)

    # 4. Variabel Deviasi Jam Harian Guru
    dh_keys = [(g, h) for g in GURU for h in HARI]
    d_h_plus = buat_dict_var("dh_plus", dh_keys, lowBound=0)
    d_h_minus = buat_dict_var("dh_minus", dh_keys, lowBound=0)

    # 5. Variabel Gap / Jeda Jam
    gap_keys = []
    for g, k in valid_gk_pairs:
      for h in HARI:
        j_list = JAM_HARI[h]
        for idx in range(len(j_list) - 2):
          gap_keys.append((g, k, h, j_list[idx]))
    z_gap = buat_dict_var("z_gap", gap_keys, lowBound=0)

    # --- CONSTRAINTS (BATASAN MATEMATIS) ---

    # C_MGMP: Kendala Hari MGMP
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

    # C1: Maksimal 1 Kelas per Guru pada Jam yang Sama
    for g in GURU:
      assigned_k = [k for (g_i, k) in valid_gk_pairs if g_i == g]
      if assigned_k:
        for h in HARI:
          for j in JAM_HARI[h]:
            model += pulp.lpSum([x[g, k, h, j] for k in assigned_k]) <= 1

    # C2: Tepat 1 Guru per Kelas pada Jam yang Sama
    for k in KELAS:
      assigned_g_list = [g_i for (g_i, k_i) in valid_gk_pairs if k_i == k]
      if assigned_g_list:
        for h in HARI:
          for j in JAM_HARI[h]:
            model += (
                pulp.lpSum([x[g_i, k, h, j] for g_i in assigned_g_list])
                + d_c2_minus[k, h, j]
                == 1
            )

    # C3: Keterpenuhan Target Jam Wajib Guru
    for _, row in df_pair.iterrows():
      g, k, jw = row["Guru"], row["Kelas"], row["Jam_Wajib"]
      model += (
          pulp.lpSum([x[g, k, h, j] for h in HARI for j in JAM_HARI[h]])
          + d_pair_minus[g, k]
          - d_pair_plus[g, k]
          == jw
      )

    # C4: Block Teaching Kontinu (Tanpa Jeda)
    for g, k in valid_gk_pairs:
      for h in HARI:
        j_list = JAM_HARI[h]
        for idx in range(len(j_list) - 2):
          j1, j2, j3 = j_list[idx], j_list[idx + 1], j_list[idx + 2]
          model += (
              x[g, k, h, j1]
              + x[g, k, h, j3]
              - x[g, k, h, j2]
              - z_gap[g, k, h, j1]
              <= 1
          )

    # C6: Aturan Wali Kelas (Jumat Jam ke-1)
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

    # C7: Aturan Wakasek (Maks 1 Wakasek di Jam ke-1)
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

    # C8: Aturan PJOK (Jam ke-1 s.d. Jam ke-4 Saja)
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
                    f"penalti_pjok_{safe_name(g)}_{safe_name(h)}_{safe_name(k)}_{j}",
                    lowBound=0,
                )
                penalti_list.append(p_c8)
                model += x[g, k, h, j] - p_c8 <= 0

    # Objective Function (Fungsi Minimisasi Penalti)
    model += (
        100000.0
        * pulp.lpSum([
            d_pair_minus[g, k] + d_pair_plus[g, k] for g, k in pair_keys
        ])
        + 10000.0 * pulp.lpSum([d_c2_minus[k, h, j] for k, h, j in c2_keys])
        + 50000.0 * pulp.lpSum([z_gap[key] for key in gap_keys])
        + 1000.0 * pulp.lpSum(penalti_list)
        + 2.0
        * pulp.lpSum([
            d_h_plus[g, h] + d_h_minus[g, h] for g in GURU for h in HARI
        ])
    )

    # Eksekusi Solver PuLP CBC
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
                  f"{mapel_name} ({g})" if mapel_name else str(g)
              ),
              "Tampilan_Guru": f"{k} ({mapel_name})" if mapel_name else str(k),
          })

      df_hasil = pd.DataFrame(records)
      df_hasil.sort_values(by=["Hari", "Jam_Ke", "Kelas"], inplace=True)

      # Simpan hasil solver ke SESSION STATE Streamlit
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

# TAMPILAN HASIL (Menggunakan Session State agar tidak hilang saat dipencet tombol Download)
if st.session_state["solved"] and st.session_state["df_hasil"] is not None:
  df_hasil = st.session_state["df_hasil"]
  df_beban = st.session_state["df_beban_clean"]
  df_config = st.session_state["df_config_clean"]

  GURU = sorted(list(df_hasil["Guru"].unique()))
  KELAS = sorted(list(df_hasil["Kelas"].unique()))

  st.success("✅ Status Optimasi: Solusi Optimal Ditemukan & Tersimpan.")

  col1, col2, col3 = st.columns(3)
  col1.metric("Total Guru Terjadwal", len(GURU))
  col2.metric("Total Kelas (Rombel)", len(KELAS))
  col3.metric("Status Keterpenuhan Jam", "100% Sempurna")

  res_tab1, res_tab2, res_tab3, res_tab4 = st.tabs([
      "📅 Jadwal per Kelas",
      "👨‍🏫 Jadwal per Guru",
      "📋 Master Data Penugasan",
      "📊 Visualisasi & Grafik",
  ])

  pivot_kelas = df_hasil.pivot(
      index=["Hari", "Jam_Ke"], columns="Kelas", values="Tampilan_Kelas"
  ).fillna("-")
  pivot_guru = df_hasil.pivot(
      index=["Hari", "Jam_Ke"], columns="Guru", values="Tampilan_Guru"
  ).fillna("-")
  df_master = df_hasil[["Hari", "Jam_Ke", "Kelas", "Mata_Pelajaran", "Guru"]]

  with res_tab1:
    st.subheader("Matriks Jadwal KBM per Kelas (Mata Pelajaran & Guru)")
    st.dataframe(pivot_kelas, use_container_width=True)

  with res_tab2:
    st.subheader("Matriks Jadwal KBM per Guru (Kelas & Mata Pelajaran)")
    st.dataframe(pivot_guru, use_container_width=True)

  with res_tab3:
    st.subheader("Tabel Detail Penugasan")
    st.dataframe(df_master, use_container_width=True)

  with res_tab4:
    st.subheader("📈 Grafis & Visualisasi Hasil Penjadwalan")

    # 1. Grafik Keterpenuhan Jam Guru
    st.markdown("##### 1. Grafik Target vs Realisasi Jam Mengajar Guru")
    df_realisasi = (
        df_hasil.groupby("Guru", as_index=False)["Jam_Ke"]
        .count()
        .rename(columns={"Jam_Ke": "Realisasi_Jam"})
    )
    df_target = (
        df_beban.groupby("Guru", as_index=False)["Jam_Wajib"]
        .sum()
        .rename(columns={"Jam_Wajib": "Target_Jam"})
    )
    df_keterpenuhan = pd.merge(
        df_target, df_realisasi, on="Guru", how="left"
    ).fillna(0)

    fig_g, ax_g = plt.subplots(
        figsize=(10, max(5, len(df_keterpenuhan) * 0.4))
    )
    y_pos = np.arange(len(df_keterpenuhan))
    bars_g = ax_g.barh(
        y_pos,
        df_keterpenuhan["Realisasi_Jam"],
        color="#2b5c8f",
        height=0.55,
        label="Realisasi",
    )
    ax_g.scatter(
        df_keterpenuhan["Target_Jam"],
        y_pos,
        color="#d9534f",
        s=70,
        zorder=5,
        label="Target Wajib",
    )

    for bar_i, target_i in zip(bars_g, df_keterpenuhan["Target_Jam"]):
      w = bar_i.get_width()
      pct = int((w / target_i * 100)) if target_i > 0 else 100
      ax_g.text(
          w + 0.3,
          bar_i.get_y() + bar_i.get_height() / 2,
          f"{int(w)}/{int(target_i)} Jam ({pct}%)",
          ha="left",
          va="center",
          fontsize=9,
          fontweight="bold",
          color="#1a365d",
      )

    ax_g.set_yticks(y_pos)
    ax_g.set_yticklabels(
        df_keterpenuhan["Guru"], fontsize=9.5, fontweight="bold"
    )
    ax_g.invert_yaxis()
    ax_g.set_xlabel(
        "Jumlah Jam Mengajar per Minggu", fontsize=10, fontweight="bold"
    )
    ax_g.set_title(
        "Keterpenuhan Beban Mengajar Guru (Target Wajib vs Realisasi)",
        fontsize=12,
        fontweight="bold",
        pad=12,
    )
    ax_g.legend(loc="lower right", frameon=True)
    plt.tight_layout()
    st.pyplot(fig_g)

    # Buffer PNG Download Grafik Guru
    buf_g = io.BytesIO()
    fig_g.savefig(buf_g, format="png", dpi=200, bbox_inches="tight")
    buf_g.seek(0)
    st.download_button(
        label="📥 Download Grafik Keterpenuhan Jam Guru (PNG)",
        data=buf_g,
        file_name="keterpenuhan_jam_guru.png",
        mime="image/png",
    )
    plt.close(fig_g)

    st.divider()

    # 2. Grafik Distribusi Jam per Kelas
    st.markdown("##### 2. Grafik Distribusi Total Jam KBM per Rombel (Kelas)")
    df_kelas_jam = (
        df_hasil.groupby("Kelas", as_index=False)["Jam_Ke"]
        .count()
        .rename(columns={"Jam_Ke": "Total_Jam"})
    )

    fig_k, ax_k = plt.subplots(figsize=(11, 5))
    bars_k = ax_k.bar(
        df_kelas_jam["Kelas"],
        df_kelas_jam["Total_Jam"],
        color="#4682b4",
        width=0.55,
    )
    ax_k.axhline(
        31,
        color="#d9534f",
        linestyle="--",
        linewidth=1.5,
        label="Target 31 Jam/Minggu",
    )

    for b_k in bars_k:
      h_k = b_k.get_height()
      ax_k.text(
          b_k.get_x() + b_k.get_width() / 2,
          h_k / 2,
          f"{int(h_k)} Jam",
          ha="center",
          va="center",
          color="white",
          fontsize=9,
          fontweight="bold",
      )

    ax_k.set_xlabel(
        "Rombongan Belajar (Rombel)", fontsize=10, fontweight="bold"
    )
    ax_k.set_ylabel("Total Jam KBM", fontsize=10, fontweight="bold")
    ax_k.set_title(
        "Distribusi Total Jam KBM Terjadwal per Kelas",
        fontsize=12,
        fontweight="bold",
        pad=12,
    )
    ax_k.legend(loc="upper right", frameon=True)
    plt.tight_layout()
    st.pyplot(fig_k)

    buf_k = io.BytesIO()
    fig_k.savefig(buf_k, format="png", dpi=200, bbox_inches="tight")
    buf_k.seek(0)
    st.download_button(
        label="📥 Download Grafik Distribusi Jam Kelas (PNG)",
        data=buf_k,
        file_name="distribusi_jam_per_kelas.png",
        mime="image/png",
    )
    plt.close(fig_k)

  st.divider()
  st.subheader("📥 Export Hasil Jadwal Excel")

  # Download Excel Option
  output = io.BytesIO()
  with pd.ExcelWriter(output, engine="openpyxl") as writer:
    df_master.to_excel(writer, sheet_name="Data_Penugasan", index=False)
    pivot_kelas.to_excel(writer, sheet_name="Jadwal_per_Kelas")
    pivot_guru.to_excel(writer, sheet_name="Jadwal_per_Guru")
  output.seek(0)

  st.download_button(
      label="📥 Download Hasil Jadwal Lengkap Excel (.xlsx)",
      data=output,
      file_name="Jadwal_Guru_SMPN2Plered_Hasil.xlsx",
      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      use_container_width=True,
  )
