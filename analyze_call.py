import streamlit as st
from openai import OpenAI
import json
import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import tempfile

OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
SHEET_NAME     = "call_analyze"
CREDS_FILE     = "credentials.json"

client = OpenAI(api_key=OPENAI_API_KEY)

def get_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=scopes)
    gc = gspread.authorize(creds)
    sheet = gc.open(SHEET_NAME).sheet1
    if not sheet.row_values(1):
        sheet.append_row(["Менеджер", "Файл", "Дата", "Скрипт", "Возражения", "Настроение", "Сильные стороны", "Ошибки", "Рекомендации"])
    return sheet

def transcribe_audio(path):
    with open(path, "rb") as f:
        return client.audio.transcriptions.create(model="gpt-4o-transcribe", file=f).text

def analyze_call(transcript_text):
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "Ты эксперт по контролю качества звонков продаж."},
            {"role": "user", "content": f"Проанализируй звонок:\n\n{transcript_text}\n\nВерни JSON:\n- script_score (0-100)\n- objection_score (0-100)\n- client_sentiment (positive / neutral / negative)\n- strengths (list, на русском)\n- mistakes (list, на русском)\n- recommendations (list, на русском)"}
        ]
    )
    return json.loads(response.choices[0].message.content)

st.set_page_config(page_title="Контроль качества звонков", page_icon="📞", layout="centered")
st.title("📞 Контроль качества звонков")

manager_name  = st.text_input("Имя менеджера", placeholder="Иван Петров")
uploaded_file = st.file_uploader("Загрузи аудиофайл", type=["mp3", "m4a", "wav", "ogg"])

if uploaded_file and manager_name:
    if st.button("▶ Анализировать"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name
        try:
            with st.spinner("Транскрипция..."): transcript = transcribe_audio(tmp_path)
            with st.spinner("Анализ..."): analysis = analyze_call(transcript)
            os.unlink(tmp_path)

            try:
                sheet = get_sheet()
                sheet.append_row([manager_name, uploaded_file.name, datetime.now().strftime("%d.%m.%Y %H:%M"), analysis["script_score"], analysis["objection_score"], analysis["client_sentiment"], ", ".join(analysis["strengths"]), ", ".join(analysis["mistakes"]), ", ".join(analysis["recommendations"])])
                st.success("✓ Сохранено в Google Sheets")
            except Exception as e:
                st.error(f"Google Sheets: {e}")

            c1, c2, c3 = st.columns(3)
            with c1: st.metric("Скрипт", f"{analysis['script_score']}/100")
            with c2: st.metric("Возражения", f"{analysis['objection_score']}/100")
            with c3: st.metric("Настроение", analysis['client_sentiment'])

            st.subheader("✓ Сильные стороны")
            for s in analysis["strengths"]: st.write(f"• {s}")
            st.subheader("✗ Ошибки")
            for m in analysis["mistakes"]: st.write(f"• {m}")
            st.subheader("→ Рекомендации")
            for r in analysis["recommendations"]: st.write(f"• {r}")

            with st.expander("📄 Текст звонка"): st.text(transcript)

        except Exception as e:
            if os.path.exists(tmp_path): os.unlink(tmp_path)
            st.error(f"Ошибка: {e}")
elif uploaded_file and not manager_name:
    st.info("Введи имя менеджера.")