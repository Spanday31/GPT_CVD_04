import streamlit as st
import math
import pandas as pd
import matplotlib.pyplot as plt
from fpdf import FPDF
from io import BytesIO
from PIL import Image
from datetime import datetime

# ======================
# CONSTANTS
# ======================

LDL_THERAPIES = {
    "Atorvastatin 20 mg": {"reduction": 40},
    "Atorvastatin 80 mg": {"reduction": 50},
    "Rosuvastatin 10 mg": {"reduction": 45},
    "Rosuvastatin 20 mg": {"reduction": 55}
}

# ======================
# CALCULATION FUNCTIONS
# ======================

@st.cache_data
def calculate_smart_risk(age, sex, sbp, total_chol, hdl, smoker, diabetes, egfr, crp, vasc_count):
    try:
        sex_val = 1 if sex == "Male" else 0
        smoking_val = 1 if smoker else 0
        diabetes_val = 1 if diabetes else 0
        crp_log = math.log(crp + 1)
        lp = (0.064 * age + 0.34 * sex_val + 0.02 * sbp + 0.25 * total_chol -
              0.25 * hdl + 0.44 * smoking_val + 0.51 * diabetes_val -
              0.2 * (egfr / 10) + 0.25 * crp_log + 0.4 * vasc_count)
        risk10 = 1 - 0.900 ** math.exp(lp - 5.8)
        return max(1.0, min(99.0, round(risk10 * 100, 1)))
    except Exception as e:
        st.error(f"Error calculating risk: {str(e)}")
        return None

def calculate_ldl_effect(baseline_risk, baseline_ldl, final_ldl):
    try:
        ldl_reduction = baseline_ldl - final_ldl
        rrr = min(22 * ldl_reduction, 60)
        return baseline_risk * (1 - rrr / 100)
    except Exception as e:
        st.error(f"Error calculating LDL effect: {str(e)}")
        return baseline_risk

def calculate_ldl_reduction(current_ldl, pre_statin, discharge_statin, discharge_add_ons):
    statin_reduction = LDL_THERAPIES.get(discharge_statin, {}).get("reduction", 0)
    if pre_statin != "None":
        statin_reduction *= 0.5
    total_reduction = statin_reduction
    if "Ezetimibe" in discharge_add_ons:
        total_reduction += 20
    if "PCSK9 inhibitor" in discharge_add_ons:
        total_reduction += 60
    if "Inclisiran" in discharge_add_ons:
        total_reduction += 50
    projected_ldl = current_ldl * (1 - total_reduction / 100)
    return projected_ldl, total_reduction

def generate_recommendations(final_risk):
    if final_risk >= 30:
        return "🔴 Very High Risk: High-intensity statin, PCSK9 inhibitor, SBP <130 mmHg."
    elif final_risk >= 20:
        return "🟠 High Risk: Moderate-intensity statin, SBP <130 mmHg."
    else:
        return "🟢 Moderate Risk: Lifestyle adherence, annual reassessment."

# ======================
# PDF REPORT GENERATION
# ======================

class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'PRIME CVD Risk Assessment Report', 0, 1, 'C')

def create_pdf_report(patient_data, risk_data):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, 'PRIME CVD Risk Assessment', 0, 1, 'C')
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f"Patient: {patient_data['name']}, Age: {patient_data['age']}, Sex: {patient_data['sex']}", 0, 1)
    pdf.cell(0, 10, f"Baseline Risk: {risk_data['baseline_risk']}%", 0, 1)
    pdf.cell(0, 10, f"Final Risk: {risk_data['final_risk']}%", 0, 1)
    pdf.cell(0, 10, f"Current LDL: {risk_data['current_ldl']} mmol/L", 0, 1)
    pdf.cell(0, 10, f"Target LDL: {risk_data['ldl_target']} mmol/L", 0, 1)
    pdf.multi_cell(0, 10, f"Recommendations: {risk_data['recommendations']}")
    return pdf.output(dest='S').encode('latin1')

# ======================
# STREAMLIT APP SETUP
# ======================

st.set_page_config(page_title="PRIME CVD Risk Calculator", layout="wide", page_icon="❤️")

st.title("PRIME CVD Risk Calculator")

st.sidebar.header("Patient Demographics")
age = st.sidebar.number_input("Age", 30, 100, 65)
sex = st.sidebar.radio("Sex", ["Male", "Female"], horizontal=True)
diabetes = st.sidebar.checkbox("Diabetes mellitus")
smoker = st.sidebar.checkbox("Current smoker")

st.sidebar.header("Vascular Disease")
cad = st.sidebar.checkbox("Coronary artery disease")
stroke = st.sidebar.checkbox("Cerebrovascular disease")
pad = st.sidebar.checkbox("Peripheral artery disease")
vasc_count = sum([cad, stroke, pad])

st.sidebar.header("Biomarkers")
total_chol = st.sidebar.number_input("Total Cholesterol (mmol/L)", 2.0, 10.0, 5.0, 0.1)
hdl = st.sidebar.number_input("HDL-C (mmol/L)", 0.5, 3.0, 1.0, 0.1)
ldl = st.sidebar.number_input("LDL-C (mmol/L)", 0.5, 6.0, 3.5, 0.1)
sbp = st.sidebar.number_input("SBP (mmHg)", 90, 220, 140)
egfr = st.sidebar.slider("eGFR (mL/min/1.73m²)", 15, 120, 80)
crp = st.sidebar.number_input("hs-CRP (mg/L)", 0.1, 20.0, 2.0, 0.1)

# ======================
# MAIN LOGIC
# ======================

baseline_risk = calculate_smart_risk(age, sex, sbp, total_chol, hdl, smoker, diabetes, egfr, crp, vasc_count)

if baseline_risk:
    st.success(f"Baseline 10-Year Risk: {baseline_risk}%")

    pre_statin = st.selectbox("Current Statin", ["None"] + list(LDL_THERAPIES.keys()), index=0)
    discharge_statin = st.selectbox("Recommended Statin", ["None"] + list(LDL_THERAPIES.keys()), index=2)
    discharge_add_ons = st.multiselect("Recommended Add-ons", ["Ezetimibe", "PCSK9 inhibitor", "Inclisiran"])
    target_ldl = st.slider("LDL-C Target (mmol/L)", 0.5, 3.0, 1.4, 0.1)

    if st.button("Calculate Treatment Impact"):
        projected_ldl, total_reduction = calculate_ldl_reduction(ldl, pre_statin, discharge_statin, discharge_add_ons)
        final_risk = calculate_ldl_effect(baseline_risk, ldl, projected_ldl)
        recommendations = generate_recommendations(final_risk)

        st.metric("Projected LDL-C", f"{projected_ldl:.1f} mmol/L", delta=f"{total_reduction:.0f}% reduction")
        st.metric("Post-Treatment Risk", f"{final_risk:.1f}%", delta=f"{baseline_risk - final_risk:.1f}% absolute reduction")
        st.subheader("Clinical Recommendations")
        st.write(recommendations)

        patient_name = st.text_input("Patient Name for Report", placeholder="Enter patient name")
        if st.button("Generate PDF Report") and patient_name:
            pdf_bytes = create_pdf_report(
                patient_data={'name': patient_name, 'age': age, 'sex': sex},
                risk_data={'baseline_risk': baseline_risk, 'final_risk': final_risk, 'current_ldl': ldl,
                           'ldl_target': target_ldl, 'recommendations': recommendations}
            )
            st.download_button(label="⬇️ Download Report", data=pdf_bytes,
                               file_name=f"{patient_name.replace(' ', '_')}_CVD_Report.pdf", mime="application/pdf")
else:
    st.warning("Please complete all patient data to calculate risk.")
