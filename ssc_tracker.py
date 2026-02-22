import streamlit as st
from google.cloud import firestore
import random
import pandas as pd
import json
import re

# --- 1. Database Setup ---
key_dict = json.loads(st.secrets["textkey"])
db = firestore.Client.from_service_account_info(key_dict)

def fetch_all_words():
    docs = db.collection("vocabulary_master").stream()
    words = [doc.to_dict() for doc in docs]
    # Sort alphabetically
    return sorted(words, key=lambda x: x['word_text'].lower())

def update_score(word_text, is_correct, quiz_type):
    doc_ref = db.collection("vocabulary_master").document(word_text)
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        new_total = data.get('total_attempts', 0) + 1
        new_correct = data.get('correct_attempts', 0) + (1 if is_correct else 0)
        
        # Track which quiz type was attempted to mark sets as completed
        attempted_key = f"{quiz_type}_attempted"
        
        doc_ref.update({
            'total_attempts': new_total,
            'correct_attempts': new_correct,
            attempted_key: True
        })

# --- 2. Custom Interactive Buttons (Red/Green Logic) ---
def render_quiz_options(options, correct_option, word_text, quiz_type):
    if st.session_state.get('answered', False):
        for opt in options:
            if opt == correct_option:
                # Highlight correct answer in Green
                st.markdown(f"<div style='background-color: #d4edda; color: #155724; padding: 15px; border-radius: 8px; border: 1px solid #c3e6cb; margin-bottom: 10px; font-weight: bold;'>✅ {opt}</div>", unsafe_allow_html=True)
            elif opt == st.session_state.selected_option:
                # Highlight chosen wrong answer in Red
                st.markdown(f"<div style='background-color: #f8d7da; color: #721c24; padding: 15px; border-radius: 8px; border: 1px solid #f5c6cb; margin-bottom: 10px;'>❌ {opt}</div>", unsafe_allow_html=True)
            else:
                # Neutral for unselected wrong answers
                st.markdown(f"<div style='background-color: #f8f9fa; color: #6c757d; padding: 15px; border-radius: 8px; border: 1px solid #dee2e6; margin-bottom: 10px;'>{opt}</div>", unsafe_allow_html=True)
        
        if st.button("Next Question ➡️"):
            st.session_state.current_index += 1
            st.session_state.answered = False
            st.session_state.selected_option = None
            st.rerun()
    else:
        for opt in options:
            if st.button(opt, key=opt, use_container_width=True):
                st.session_state.answered = True
                st.session_state.selected_option = opt
                is_correct = (opt == correct_option)
                update_score(word_text, is_correct, quiz_type)
                st.rerun()

# --- 3. Streamlit UI & Navigation ---
st.set_page_config(page_title="SSC CGL Vocab Tracker", layout="centered")
st.title("📚 SSC CGL Tracker - Target: May 31")

menu = st.sidebar.selectbox("Navigation", ["Home / Upload PDF", "OWS Quiz (Sets of 25)", "Synonym Quiz (Sets of 25)"])

# ----------------------------------------
# TAB 1: UPLOAD & PDF EXTRACTION
# ----------------------------------------
if menu == "Home / Upload PDF":
    st.header("📥 Smart PDF Uploader")
    st.write("Upload a PDF table. The program will automatically separate Synonyms from the English Meaning and add them to your database alphabetically.")
    
    uploaded_pdf = st.file_uploader("Choose a PDF file", type="pdf")
    
    if uploaded_pdf is not None:
        if st.button("Extract & Add Words"):
            import pdfplumber
            with st.spinner("Extracting meanings and synonyms..."):
                vocab_ref = db.collection("vocabulary_master")
                added_count = 0
                
                with pdfplumber.open(uploaded_pdf) as pdf:
                    for page in pdf.pages:
                        table = page.extract_table()
                        if not table: continue
                            
                        for row in table[1:]:
                            if not row or len(row) < 3: continue
                                
                            word_raw = str(row[1]).strip()
                            meaning_raw = str(row[2]).strip()
                            
                            if not word_raw or word_raw == "Word (POS)": continue
                                
                            # 1. Clean the Word
                            word_clean = word_raw.split('(')[0].strip()
                            
                            # 2. Split Synonyms and English Meaning
                            # In your PDF, they are separated by a newline
                            parts = meaning_raw.split('\n')
                            if len(parts) >= 2:
                                synonyms_text = parts[0].strip()
                                english_meaning_text = " ".join(parts[1:]).strip()
                            else:
                                synonyms_text = "No synonyms provided"
                                english_meaning_text = meaning_raw.strip()
                            
                            doc_ref = vocab_ref.document(word_clean)
                            if not doc_ref.get().exists:
                                doc_ref.set({
                                    'word_text': word_clean,
                                    'english_meaning': english_meaning_text,
                                    'synonyms': synonyms_text,
                                    'correct_attempts': 0,
                                    'total_attempts': 0,
                                    'ows_attempted': False,
                                    'syno_attempted': False
                                })
                                added_count += 1
                                
                st.success(f"✅ Success! {added_count} new words added to your quiz database.")

# ----------------------------------------
# TAB 2 & 3: QUIZ LOGIC (OWS & SYNONYMS)
# ----------------------------------------
elif menu in ["OWS Quiz (Sets of 25)", "Synonym Quiz (Sets of 25)"]:
    quiz_type = "ows" if "OWS" in menu else "syno"
    st.header(f"🧠 {menu.split(' ')[0]} Practice")
    
    all_words = fetch_all_words()
    
    if not all_words:
        st.warning("Your database is empty. Please upload a PDF first.")
    else:
        # Chunk into sets of 25
        sets = [all_words[i:i + 25] for i in range(0, len(all_words), 25)]
        
        # Create user-friendly labels for the dropdown
        set_options = {}
        for i, s in enumerate(sets):
            start_word = s[0]['word_text']
            end_word = s[-1]['word_text']
            
            # Check if all words in this set have been attempted
            is_attempted = all(w.get(f'{quiz_type}_attempted', False) for w in s)
            status = "✅ Attempted" if is_attempted else "⏳ Pending"
            
            label = f"Set {i+1}: {start_word} to {end_word} [{status}]"
            set_options[label] = s
            
        selected_set_label = st.selectbox("Choose a Practice Set:", list(set_options.keys()))
        current_set = set_options[selected_set_label]
        
        # Quiz initialization
        if 'active_set_label' not in st.session_state or st.session_state.active_set_label != selected_set_label:
            st.session_state.active_set_label = selected_set_label
            st.session_state.current_index = 0
            st.session_state.answered = False
            
        # Run the 25-question loop
        if st.session_state.current_index < len(current_set):
            st.progress((st.session_state.current_index) / len(current_set))
            q_data = current_set[st.session_state.current_index]
            
            st.subheader(f"Question {st.session_state.current_index + 1} of {len(current_set)}")
            
            # Formulate Question and Options based on Quiz Type
            if quiz_type == "ows":
                st.info(f"**Find the word for:**\n\n{q_data.get('english_meaning', 'No meaning found')}")
                correct_ans = q_data['word_text']
                pool = [w['word_text'] for w in all_words if w['word_text'] != correct_ans]
                
            else:
                st.info(f"**Find a synonym for:**\n\n### {q_data['word_text']}")
                # Extract one synonym from the comma-separated string
                syn_list = [s.strip() for s in q_data.get('synonyms', '').split(',') if s.strip()]
                correct_ans = random.choice(syn_list) if syn_list and syn_list[0] != "No synonyms provided" else q_data.get('english_meaning', 'No synonym')
                
                # Get random wrong synonyms from other words
                pool = []
                for w in all_words:
                    if w['word_text'] != q_data['word_text']:
                        wrong_syns = [s.strip() for s in w.get('synonyms', '').split(',') if s.strip()]
                        pool.extend(wrong_syns)
            
            # Generate 4 options (1 correct, 3 decoys)
            if 'options_generated_for' not in st.session_state or st.session_state.options_generated_for != st.session_state.current_index:
                decoys = random.sample(pool, min(len(pool), 3))
                while len(decoys) < 3: decoys.append("None of the above")
                
                options = decoys + [correct_ans]
                random.shuffle(options)
                
                st.session_state.current_options = options
                st.session_state.correct_ans = correct_ans
                st.session_state.options_generated_for = st.session_state.current_index

            # Render the interactive red/green buttons
            render_quiz_options(st.session_state.current_options, st.session_state.correct_ans, q_data['word_text'], quiz_type)

        else:
            st.success("🎉 You have completed this set of 25 questions!")
            if st.button("🔄 Reattempt this Set"):
                st.session_state.current_index = 0
                st.session_state.answered = False
                st.rerun()
