import streamlit as st
from supabase import create_client, Client
import random
import time
import io
import uuid
from PIL import Image, ImageDraw, ImageFont
import pandas as pd
from datetime import datetime
import os
import json

# --- Initial Setup ---
st.set_page_config(
    page_title="Number and Form System",
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- CSS Styling ---
st.markdown("""
<style>
    .main-header {text-align: center; margin-bottom: 30px;}
    .number-display {font-size: 72px; text-align: center; margin: 30px 0;}
    .success-msg {background-color: #d4edda; color: #155724; padding: 10px; border-radius: 5px;}
    .error-msg {background-color: #f8d7da; color: #721c24; padding: 10px; border-radius: 5px;}
    .form-box {border: 1px solid #ccc; padding: 20px; border-radius: 10px; margin: 10px 0;}
</style>
""", unsafe_allow_html=True)

# --- Functions ---

def get_supabase_client() -> Client:
    """Establishes connection to Supabase"""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        st.error("Supabase credentials not configured!")
        return None
    try:
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        st.error(f"Connection error: {str(e)}")
        return None

def check_table_exists(supabase, table_name):
    """Checks if table exists in Supabase"""
    try:
        supabase.table(table_name).select("*").limit(1).execute()
        return True
    except Exception:
        return False

# ... (Funções existentes para reuniões - manter igual)

def create_form_table_structure(supabase):
    """Cria estrutura das tabelas de formulário"""
    try:
        tables = ["forms_metadata", "questions", "responses"]
        for table in tables:
            if not check_table_exists(supabase, table):
                supabase.rpc("execute_sql", {"query": f"""
                    CREATE TABLE public.{table} (
                        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                        {"form_id UUID REFERENCES forms_metadata(id)," if table != "forms_metadata" else ""}
                        {"meeting_table_name TEXT NOT NULL," if table == "forms_metadata" else ""}
                        {"form_title TEXT NOT NULL," if table == "forms_metadata" else ""}
                        {"question_text TEXT NOT NULL," if table == "questions" else ""}
                        {"question_type TEXT NOT NULL," if table == "questions" else ""}
                        {"options JSONB," if table == "questions" else ""}
                        {"user_id TEXT NOT NULL," if table == "responses" else ""}
                        {"answers JSONB NOT NULL," if table == "responses" else ""}
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """}).execute()
        return True
    except Exception as e:
        st.error(f"Erro na criação das tabelas: {str(e)}")
        return False

def generate_form_link(form_id):
    """Gera link do formulário"""
    base_url = "https://your-app-url.streamlit.app"
    return f"{base_url}/?form={form_id}&user_id={st.session_state['user_id']}"

# --- Session State ---
if "user_id" not in st.session_state:
    st.session_state["user_id"] = str(uuid.uuid4())

# --- Query Params Handling ---
query_params = st.query_params
mode = query_params.get("mode", "master")
form_id = query_params.get("form", None)

# --- Form Handling ---
if form_id:
    supabase = get_supabase_client()
    if not supabase:
        st.stop()
    
    try:
        form_data = supabase.table("forms_metadata").select("*").eq("id", form_id).execute().data[0]
        questions = supabase.table("questions").select("*").eq("form_id", form_id).execute().data
        
        st.title(form_data["form_title"])
        
        # Verificar resposta existente
        response_exists = supabase.table("responses").select("*").eq("form_id", form_id).eq("user_id", st.session_state["user_id"]).execute().data
        if response_exists:
            st.warning("Você já respondeu este formulário!")
            st.stop()
        
        # Coletar respostas
        answers = {}
        with st.form("form_respostas"):
            for q in questions:
                if q["question_type"] == "text":
                    answers[str(q["id"])] = st.text_input(q["question_text"])
                elif q["question_type"] == "multiple_choice":
                    options = q["options"] or []
                    selected = st.multiselect(q["question_text"], options)
                    answers[str(q["id"])] = selected
            
            if st.form_submit_button("Enviar"):
                supabase.table("responses").insert({
                    "form_id": form_id,
                    "user_id": st.session_state["user_id"],
                    "answers": answers
                }).execute()
                st.success("Respostas enviadas com sucesso!")
                time.sleep(2)
                st.rerun()
                
    except Exception as e:
        st.error(f"Erro ao carregar formulário: {str(e)}")
    st.stop()

# --- Modo Participante (Números) --- 
# ... (Manter código existente do modo participante)

# --- Modo Mestre ---
else:
    valid_pages = [
        "Gerenciar Reuniões",
        "Compartilhar Links",
        "Estatísticas",
        "Formulários",
        "Respostas"
    ]
    
    st.sidebar.title("Menu Mestre")
    page = st.sidebar.radio("Navegação", valid_pages)
    
    # Página: Gerenciar Formulários
    if page == "Formulários":
        st.header("📝 Gerenciar Formulários")
        
        supabase = get_supabase_client()
        if not supabase:
            st.stop()
        
        create_form_table_structure(supabase)
        
        # Selecionar Reunião
        meetings = supabase.table("meetings_metadata").select("*").execute().data
        selected_meeting = st.selectbox("Selecione uma Reunião", meetings, format_func=lambda m: m["meeting_name"])
        
        # Criar Novo Formulário
        with st.expander("➕ Novo Formulário"):
            with st.form("novo_form"):
                title = st.text_input("Título do Formulário")
                num_questions = st.number_input("Número de Perguntas", 1, 20, 3)
                
                if st.form_submit_button("Criar"):
                    try:
                        new_form = supabase.table("forms_metadata").insert({
                            "meeting_table_name": selected_meeting["table_name"],
                            "form_title": title
                        }).execute().data[0]
                        
                        questions = []
                        for i in range(num_questions):
                            questions.append({
                                "form_id": new_form["id"],
                                "question_text": f"Pergunta {i+1}",
                                "question_type": "text"
                            })
                        
                        supabase.table("questions").insert(questions).execute()
                        st.success("Formulário criado!")
                    except Exception as e:
                        st.error(f"Erro: {str(e)}")
        
        # Listar Formulários Existentes
        forms = supabase.table("forms_metadata").select("*").eq("meeting_table_name", selected_meeting["table_name"]).execute().data
        for form in forms:
            cols = st.columns([4,1,1])
            cols[0].subheader(form["form_title"])
            cols[1].markdown(f"[🔗 Link]({generate_form_link(form['id'])})")
            if cols[2].button("Excluir", key=f"del_{form['id']}"):
                supabase.table("forms_metadata").delete().eq("id", form["id"]).execute()
                st.rerun()
    
    # Página: Respostas
    elif page == "Respostas":
        st.header("📊 Respostas Coletadas")
        
        supabase = get_supabase_client()
        if not supabase:
            st.stop()
        
        forms = supabase.table("forms_metadata").select("*").execute().data
        selected_form = st.selectbox("Selecione um Formulário", forms, format_func=lambda f: f["form_title"])
        
        responses = supabase.table("responses").select("*").eq("form_id", selected_form["id"]).execute().data
        questions = supabase.table("questions").select("*").eq("form_id", selected_form["id"]).execute().data
        
        if responses:
            st.download_button(
                "📥 Exportar CSV",
                pd.DataFrame([{
                    **{"User": r["user_id"], "Data": r["submitted_at"]},
                    **{q["question_text"]: r["answers"].get(str(q["id"]), "") 
                     for q in questions}
                } for r in responses]).to_csv(),
                f"respostas_{selected_form['form_title']}.csv"
            )
            
            for r in responses:
                with st.expander(f"Resposta de {r['user_id']}"):
                    for q in questions:
                        st.write(f"**{q['question_text']}**")
                        st.write(r['answers'].get(str(q['id']), "Sem resposta"))
        else:
            st.info("Nenhuma resposta coletada ainda")

# ... (Manter outras páginas existentes)

if __name__ == "__main__":
    pass
