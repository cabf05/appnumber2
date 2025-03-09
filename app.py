import streamlit as st
from supabase import create_client, Client
import random
import time
import io
import uuid
from PIL import Image, ImageDraw, ImageFont
import pandas as pd
from datetime import datetime
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
    """Cria conexão com o Supabase usando Secrets"""
    try:
        return create_client(
            st.secrets["SUPABASE_URL"],
            st.secrets["SUPABASE_KEY"]
        )
    except Exception as e:
        st.error(f"Erro de conexão com o Supabase: {str(e)}")
        return None

def inicializar_banco_dados(supabase):
    """Cria todas as tabelas necessárias se não existirem"""
    try:
        # Tabela de reuniões
        supabase.rpc("execute_sql", {"query": """
            CREATE TABLE IF NOT EXISTS reunioes (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                nome TEXT NOT NULL,
                tabela_nome TEXT NOT NULL UNIQUE,
                max_numeros INT NOT NULL,
                criado_em TIMESTAMPTZ DEFAULT NOW()
            );
        """).execute()

        # Tabelas de formulários
        supabase.rpc("execute_sql", {"query": """
            CREATE TABLE IF NOT EXISTS formularios (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                reuniao_id UUID REFERENCES reunioes(id),
                titulo TEXT NOT NULL,
                descricao TEXT,
                criado_em TIMESTAMPTZ DEFAULT NOW()
            );
        """).execute()

        supabase.rpc("execute_sql", {"query": """
            CREATE TABLE IF NOT EXISTS perguntas (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                formulario_id UUID REFERENCES formularios(id) ON DELETE CASCADE,
                texto TEXT NOT NULL,
                tipo TEXT NOT NULL,
                opcoes JSONB,
                ordem INT NOT NULL,
                obrigatoria BOOLEAN DEFAULT FALSE
            );
        """).execute()

        supabase.rpc("execute_sql", {"query": """
            CREATE TABLE IF NOT EXISTS respostas (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                formulario_id UUID REFERENCES formularios(id) ON DELETE CASCADE,
                usuario_id TEXT NOT NULL,
                respostas JSONB NOT NULL,
                submetido_em TIMESTAMPTZ DEFAULT NOW()
            );
        """).execute()

        return True
    except Exception as e:
        st.error(f"Erro ao criar tabelas: {str(e)}")
        return False

# --- Estado da Sessão ---
if "user_id" not in st.session_state:
    st.session_state["user_id"] = str(uuid.uuid4())

# --- Inicialização do Supabase ---
supabase = get_supabase_client()
if supabase:
    inicializar_banco_dados(supabase)

# --- Manipulação de Parâmetros da URL ---
query_params = st.query_params
form_id = query_params.get("formulario", None)

# --- Modo Participante (Formulário) ---
if form_id and supabase:
    try:
        # Carregar formulário
        formulario = supabase.table("formularios").select("*").eq("id", form_id).single().execute().data
        perguntas = supabase.table("perguntas").select("*").eq("formulario_id", form_id).order("ordem").execute().data

        st.title(formulario["titulo"])
        if formulario.get("descricao"):
            st.markdown(f"*{formulario['descricao']}*")

        # Verificar resposta existente
        resposta_existente = supabase.table("respostas").select("*").eq("formulario_id", form_id).eq("usuario_id", st.session_state["user_id"]).execute().data
        if resposta_existente:
            st.warning("Você já respondeu este formulário!")
            st.stop()

        # Coletar respostas
        respostas = {}
        with st.form(key="formulario_participante"):
            for pergunta in perguntas:
                resposta = None
                label = f"{pergunta['texto']}{' *' if pergunta['obrigatoria'] else ''}"
                
                if pergunta["tipo"] == "texto":
                    resposta = st.text_input(label)
                elif pergunta["tipo"] == "multipla_escolha":
                    opcoes = json.loads(pergunta["opcoes"])
                    resposta = st.multiselect(label, opcoes)
                elif pergunta["tipo"] == "escolha_unica":
                    opcoes = json.loads(pergunta["opcoes"])
                    resposta = st.radio(label, opcoes)
                elif pergunta["tipo"] == "escala":
                    resposta = st.slider(label, 1, 5)
                
                if pergunta["obrigatoria"] and not resposta:
                    st.error("Campo obrigatório!")
                    st.stop()
                
                respostas[pergunta["id"]] = resposta

            if st.form_submit_button("Enviar Respostas"):
                supabase.table("respostas").insert({
                    "formulario_id": form_id,
                    "usuario_id": st.session_state["user_id"],
                    "respostas": json.dumps(respostas)
                }).execute()
                st.success("Respostas enviadas com sucesso!")
                time.sleep(2)
                st.rerun()

    except Exception as e:
        st.error(f"Erro ao carregar formulário: {str(e)}")
    st.stop()

# --- Modo Organizador ---
else:
    st.sidebar.title("Painel do Organizador")
    pagina = st.sidebar.radio("Navegação", ["Reuniões", "Formulários", "Respostas"])

    # Página: Gerenciar Reuniões
    if pagina == "Reuniões":
        st.header("📅 Gerenciar Reuniões")
        
        # Criar nova reunião
        with st.expander("➕ Nova Reunião", expanded=True):
            with st.form(key="nova_reuniao"):
                nome_reuniao = st.text_input("Nome da Reunião")
                max_numeros = st.number_input("Número Máximo de Participantes", 10, 10000, 100)
                
                if st.form_submit_button("Criar"):
                    try:
                        tabela_nome = f"reuniao_{uuid.uuid4().hex[:8]}"
                        
                        # Criar tabela de números
                        supabase.rpc("execute_sql", {"query": f"""
                            CREATE TABLE {tabela_nome} (
                                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                                numero INT NOT NULL UNIQUE,
                                atribuido BOOLEAN DEFAULT FALSE,
                                usuario_id TEXT,
                                atribuido_em TIMESTAMPTZ
                            );
                        """).execute()
                        
                        # Inserir metadados
                        reuniao = supabase.table("reunioes").insert({
                            "nome": nome_reuniao,
                            "tabela_nome": tabela_nome,
                            "max_numeros": max_numeros
                        }).execute().data[0]
                        
                        # Popular números
                        numeros = [{"numero": n} for n in range(1, max_numeros+1)]
                        for i in range(0, len(numeros), 1000):
                            supabase.table(tabela_nome).insert(numeros[i:i+1000]).execute()
                        
                        st.success(f"Reunião '{nome_reuniao}' criada! Tabela: {tabela_nome}")
                    except Exception as e:
                        st.error(f"Erro ao criar reunião: {str(e)}")

        # Listar reuniões existentes
        st.subheader("Reuniões Ativas")
        if supabase:
            reunioes = supabase.table("reunioes").select("*").execute().data
            for reuniao in reunioes:
                col1, col2 = st.columns([4,1])
                col1.markdown(f"""
                    **{reuniao['nome']}**  
                    *Números: 1-{reuniao['max_numeros']}*  
                    `Tabela: {reuniao['tabela_nome']}`
                """)
                if col2.button("Excluir", key=f"del_{reuniao['id']}"):
                    supabase.table("reunioes").delete().eq("id", reuniao["id"]).execute()
                    st.rerun()

    # Página: Formulários
    elif pagina == "Formulários" and supabase:
        st.header("📝 Gerenciar Formulários")
        
        reunioes = supabase.table("reunioes").select("*").execute().data
        reuniao_selecionada = st.selectbox("Selecione a Reunião", reunioes, format_func=lambda r: r["nome"])
        
        # Criar novo formulário
        with st.expander("➕ Novo Formulário", expanded=True):
            with st.form(key="novo_formulario"):
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
                            "opcoes": opcoes,
                            "obrigatoria": obrigatoria
                        })

                if st.form_submit_button("Criar Formulário"):
                    try:
                        # Criar formulário
                        novo_form = supabase.table("formularios").insert({
                            "reuniao_id": reuniao_selecionada["id"],
                            "titulo": titulo,
                            "descricao": descricao
                        }).execute().data[0]
                        
                        # Adicionar perguntas
                        for i, pergunta in enumerate(perguntas):
                            supabase.table("perguntas").insert({
                                "formulario_id": novo_form["id"],
                                "texto": pergunta["texto"],
                                "tipo": pergunta["tipo"],
                                "opcoes": json.dumps(pergunta["opcoes"]),
                                "ordem": i+1,
                                "obrigatoria": pergunta["obrigatoria"]
                            }).execute()
                        
                        # Gerar link
                        link_form = f"https://mynumber.streamlit.app/?formulario={novo_form['id']}&user_id={st.session_state['user_id']}"
                        st.success(f"Formulário criado! [Link do Formulário]({link_form})")
                    except Exception as e:
                        st.error(f"Erro ao criar formulário: {str(e)}")

    # Página: Respostas
    elif pagina == "Respostas" and supabase:
        st.header("📊 Visualizar Respostas")
        
        formularios = supabase.table("formularios").select("*").execute().data
        form_selecionado = st.selectbox("Selecione um Formulário", formularios, format_func=lambda f: f["titulo"])
        
        if form_selecionado:
            respostas = supabase.table("respostas").select("*").eq("formulario_id", form_selecionado["id"]).execute().data
            perguntas = supabase.table("perguntas").select("*").eq("formulario_id", form_selecionado["id"]).order("ordem").execute().data
            
            if respostas:
                # Exportar CSV
                df = pd.DataFrame([{
                    **{"Usuário": r["usuario_id"], "Data": r["submetido_em"]},
                    **{p["texto"]: json.loads(r["respostas"]).get(p["id"], "") 
                    for p in perguntas}
                } for r in respostas])
                
                st.download_button(
                    "⬇️ Exportar CSV",
                    df.to_csv(index=False),
                    f"respostas_{form_selecionado['titulo']}.csv",
                    "text/csv"
                )
                
                # Visualizar respostas
                for resposta in respostas:
                    with st.expander(f"Resposta de {resposta['usuario_id']}"):
                        respostas_data = json.loads(resposta["respostas"])
                        for pergunta in perguntas:
                            st.markdown(f"**{pergunta['texto']}**")
                            resposta = respostas_data.get(pergunta["id"], "N/A")
                            if isinstance(resposta, list):
                                st.write(", ".join(resposta))
                            else:
                                st.write(resposta)
            else:
                st.info("Nenhuma resposta coletada ainda")

if __name__ == "__main__":
    pass
