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

# --- Configuração Inicial ---
st.set_page_config(
    page_title="Sistema de Numeração e Formulários",
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- Estilos CSS ---
st.markdown("""
<style>
    .main-header {text-align: center; margin-bottom: 30px;}
    .number-display {font-size: 72px; text-align: center; margin: 30px 0;}
    .success-msg {background-color: #d4edda; color: #155724; padding: 10px; border-radius: 5px;}
    .error-msg {background-color: #f8d7da; color: #721c24; padding: 10px; border-radius: 5px;}
    .form-box {border: 1px solid #ccc; padding: 20px; border-radius: 10px; margin: 10px 0;}
</style>
""", unsafe_allow_html=True)

# --- Funções Principais ---

def get_supabase_client() -> Client:
    """Cria conexão com o Supabase"""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        st.error("Variáveis de ambiente do Supabase não configuradas!")
        return None
    try:
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        st.error(f"Erro de conexão: {str(e)}")
        return None

def criar_tabelas_necessarias(supabase):
    """Cria todas as tabelas necessárias se não existirem"""
    try:
        # Criar tabela de reuniões
        supabase.rpc("execute_sql", {"query": """
            CREATE TABLE IF NOT EXISTS meetings_metadata (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                table_name TEXT NOT NULL UNIQUE,
                meeting_name TEXT NOT NULL,
                max_number INT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """).execute()

        # Criar tabelas de formulários
        supabase.rpc("execute_sql", {"query": """
            CREATE TABLE IF NOT EXISTS forms_metadata (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                meeting_id UUID REFERENCES meetings_metadata(id),
                title TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """).execute()

        supabase.rpc("execute_sql", {"query": """
            CREATE TABLE IF NOT EXISTS questions (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                form_id UUID REFERENCES forms_metadata(id) ON DELETE CASCADE,
                question_text TEXT NOT NULL,
                question_type TEXT NOT NULL,
                options JSONB,
                ordem INT NOT NULL,
                required BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """).execute()

        supabase.rpc("execute_sql", {"query": """
            CREATE TABLE IF NOT EXISTS responses (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                form_id UUID REFERENCES forms_metadata(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL,
                answers JSONB NOT NULL,
                submitted_at TIMESTAMPTZ DEFAULT NOW()
            );
        """).execute()

        return True
    except Exception as e:
        st.error(f"Erro ao criar tabelas: {str(e)}")
        return False

def criar_tabela_reuniao(supabase, nome_reuniao, max_numero):
    """Cria uma nova tabela para uma reunião"""
    try:
        tabela_nome = f"reuniao_{uuid.uuid4().hex[:8]}"
        
        # Criar entrada na metadata
        reuniao_data = supabase.table("meetings_metadata").insert({
            "table_name": tabela_nome,
            "meeting_name": nome_reuniao,
            "max_number": max_numero
        }).execute().data[0]

        # Criar tabela de números
        supabase.rpc("execute_sql", {"query": f"""
            CREATE TABLE public.{tabela_nome} (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                number INT NOT NULL UNIQUE,
                assigned BOOLEAN DEFAULT FALSE,
                user_id TEXT,
                assigned_at TIMESTAMPTZ
            );
        """).execute()

        # Inserir números
        numeros = [{"number": n} for n in range(1, max_numero+1)]
        for i in range(0, len(numeros), 1000):
            supabase.table(tabela_nome).insert(numeros[i:i+1000]).execute()

        return reuniao_data
    except Exception as e:
        st.error(f"Erro ao criar reunião: {str(e)}")
        return None

def criar_formulario(supabase, reuniao_id, titulo, descricao, perguntas):
    """Cria um novo formulário com perguntas"""
    try:
        # Criar metadata do formulário
        form_data = supabase.table("forms_metadata").insert({
            "meeting_id": reuniao_id,
            "title": titulo,
            "description": descricao
        }).execute().data[0]

        # Adicionar perguntas
        for i, pergunta in enumerate(perguntas):
            supabase.table("questions").insert({
                "form_id": form_data["id"],
                "question_text": pergunta["texto"],
                "question_type": pergunta["tipo"],
                "options": json.dumps(pergunta.get("opcoes", [])),
                "ordem": i+1,
                "required": pergunta.get("obrigatoria", False)
            }).execute()

        return form_data
    except Exception as e:
        st.error(f"Erro ao criar formulário: {str(e)}")
        return None

# --- Estado da Sessão ---
if "user_id" not in st.session_state:
    st.session_state["user_id"] = str(uuid.uuid4())

# --- Configuração Inicial do Banco de Dados ---
supabase = get_supabase_client()
if supabase:
    criar_tabelas_necessarias(supabase)

# --- Manipulação de Parâmetros da URL ---
query_params = st.query_params
modo = query_params.get("modo", "master")
form_id = query_params.get("form_id", None)

# --- Modo Participante (Formulário) ---
if form_id and supabase:
    try:
        # Carregar dados do formulário
        form = supabase.table("forms_metadata").select("*").eq("id", form_id).single().execute().data
        perguntas = supabase.table("questions").select("*").eq("form_id", form_id).order("ordem").execute().data

        st.title(form["title"])
        st.write(form.get("description", ""))

        # Verificar resposta existente
        resposta_existente = supabase.table("responses").select("*").eq("form_id", form_id).eq("user_id", st.session_state["user_id"]).execute().data
        if resposta_existente:
            st.warning("Você já respondeu este formulário!")
            st.stop()

        # Coletar respostas
        respostas = {}
        with st.form("formulario"):
            for pergunta in perguntas:
                label = f"{pergunta['question_text']}{' *' if pergunta['required'] else ''}"
                
                if pergunta["question_type"] == "texto":
                    resposta = st.text_input(label, key=pergunta["id"])
                elif pergunta["question_type"] == "multipla_escolha":
                    opcoes = json.loads(pergunta["options"])
                    resposta = st.multiselect(label, opcoes, key=pergunta["id"])
                elif pergunta["question_type"] == "escolha_unica":
                    opcoes = json.loads(pergunta["options"])
                    resposta = st.radio(label, opcoes, key=pergunta["id"])
                elif pergunta["question_type"] == "escala":
                    resposta = st.slider(label, 1, 5, key=pergunta["id"])
                
                respostas[pergunta["id"]] = resposta

            if st.form_submit_button("Enviar Respostas"):
                # Validar campos obrigatórios
                campos_validos = True
                for pergunta in perguntas:
                    if pergunta["required"] and not respostas.get(pergunta["id"]):
                        campos_validos = False
                        st.error(f"Campo obrigatório: {pergunta['question_text']}")
                
                if campos_validos:
                    supabase.table("responses").insert({
                        "form_id": form_id,
                        "user_id": st.session_state["user_id"],
                        "answers": json.dumps(respostas)
                    }).execute()
                    st.success("Respostas enviadas com sucesso!")
                    time.sleep(2)
                    st.rerun()

    except Exception as e:
        st.error(f"Erro ao carregar formulário: {str(e)}")
    st.stop()

# --- Modo Mestre ---
else:
    st.sidebar.title("Menu do Organizador")
    pagina = st.sidebar.radio("Navegação", [
        "Gerenciar Reuniões", 
        "Criar Formulário", 
        "Visualizar Respostas"
    ])

    # Página: Gerenciar Reuniões
    if pagina == "Gerenciar Reuniões":
        st.header("📅 Gerenciar Reuniões")
        
        with st.expander("➕ Nova Reunião", expanded=True):
            with st.form("nova_reuniao"):
                nome = st.text_input("Nome da Reunião")
                max_num = st.number_input("Número Máximo de Participantes", 10, 10000, 100)
                
                if st.form_submit_button("Criar Reunião"):
                    if supabase and nome:
                        reuniao = criar_tabela_reuniao(supabase, nome, max_num)
                        if reuniao:
                            st.success(f"Reunião '{nome}' criada com sucesso! Tabela: {reuniao['table_name']}")

        st.subheader("Reuniões Existentes")
        if supabase:
            reunioes = supabase.table("meetings_metadata").select("*").execute().data
            for reuniao in reunioes:
                col1, col2 = st.columns([4,1])
                col1.write(f"**{reuniao['meeting_name']}** (Números: 1-{reuniao['max_number']})")
                col2.button("Excluir", key=f"del_{reuniao['id']}", on_click=lambda: supabase.table("meetings_metadata").delete().eq("id", reuniao["id"]).execute())

    # Página: Criar Formulário
    elif pagina == "Criar Formulário" and supabase:
        st.header("📝 Criar Novo Formulário")
        
        reunioes = supabase.table("meetings_metadata").select("*").execute().data
        reuniao_selecionada = st.selectbox("Selecione a Reunião", reunioes, format_func=lambda r: r["meeting_name"])
        
        with st.form("novo_formulario"):
            titulo = st.text_input("Título do Formulário")
            descricao = st.text_area("Descrição")
            
            st.subheader("Perguntas")
            perguntas = []
            for i in range(3):
                with st.expander(f"Pergunta {i+1}", expanded=i<2):
                    tipo = st.selectbox("Tipo", ["texto", "multipla_escolha", "escolha_unica", "escala"], key=f"tipo_{i}")
                    texto = st.text_input("Texto da Pergunta", key=f"texto_{i}")
                    obrigatoria = st.checkbox("Obrigatória", key=f"obrigatoria_{i}")
                    opcoes = []
                    
                    if tipo in ["multipla_escolha", "escolha_unica"]:
                        opcoes = st.text_area("Opções (uma por linha)", key=f"opcoes_{i}").split("\n")
                    
                    perguntas.append({
                        "tipo": tipo,
                        "texto": texto,
                        "obrigatoria": obrigatoria,
                        "opcoes": opcoes
                    })

            if st.form_submit_button("Publicar Formulário"):
                form = criar_formulario(supabase, reuniao_selecionada["id"], titulo, descricao, perguntas)
                if form:
                    link = f"{os.getenv('APP_URL')}/?form_id={form['id']}&user_id={st.session_state['user_id']}"
                    st.success(f"Formulário criado! [Link de Acesso]({link})")

    # Página: Visualizar Respostas
    elif pagina == "Visualizar Respostas" and supabase:
        st.header("📊 Respostas Coletadas")
        
        forms = supabase.table("forms_metadata").select("*").execute().data
        form_selecionado = st.selectbox("Selecione um Formulário", forms, format_func=lambda f: f["title"])
        
        if form_selecionado:
            respostas = supabase.table("responses").select("*").eq("form_id", form_selecionado["id"]).execute().data
            perguntas = supabase.table("questions").select("*").eq("form_id", form_selecionado["id"]).order("ordem").execute().data
            
            if respostas:
                st.download_button(
                    "📥 Exportar CSV",
                    pd.DataFrame([{
                        **{"Usuário": r["user_id"], "Data": r["submitted_at"]},
                        **{p["question_text"]: json.loads(r["answers"]).get(p["id"], "") 
                        for p in perguntas}
                    } for r in respostas]).to_csv(),
                    f"respostas_{form_selecionado['title']}.csv"
                )

                for resposta in respostas:
                    with st.expander(f"Resposta de {resposta['user_id']}"):
                        dados = json.loads(resposta["answers"])
                        for pergunta in perguntas:
                            st.write(f"**{pergunta['question_text']}**")
                            resposta = dados.get(pergunta["id"], "N/A")
                            if isinstance(resposta, list):
                                st.write(", ".join(resposta))
                            else:
                                st.write(resposta)
            else:
                st.info("Nenhuma resposta coletada ainda")

if __name__ == "__main__":
    pass
