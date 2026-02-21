import streamlit as st
from google.cloud import firestore
import random
import pandas as pd
import json

# --- 1. Database Setup (Firebase) ---
# Authenticate to Firestore using the JSON account key stored in Streamlit Secrets
key_dict = json.loads(st.secrets["textkey"])
db = firestore.Client.from_service_account_info(key_dict)

def init_db():
    # Firestore doesn't need table creation, but we can seed starter data if empty
    vocab_ref = db.collection("vocabulary_master")
    
    # Check if we already have data
    if len(list(vocab_ref.limit(1).stream())) == 0:
        starter_data = [
            {'word_text': 'Dermatologist', 'definition': 'A doctor who studies skin diseases', 'hindi_meaning': 'त्वचा विशेषज्ञ', 'category': 'OWS', 'repeat_count': 3, 'correct_attempts': 0, 'total_attempts': 0},
            {'word_text': 'Derelict', 'definition': 'A person without a home or property', 'hindi_meaning': 'आवारा व्यक्ति', 'category': 'OWS', 'repeat_count': 2, 'correct_attempts': 0, 'total_attempts': 0},
            {'word_text': 'Dexterous', 'definition': 'Skillful with your hands', 'hindi_meaning': 'निपुण', 'category': 'OWS', 'repeat_count': 2, 'correct_attempts': 0, 'total_attempts': 0}
        ]
        
        for data in starter_data:
            # Using the word itself as the document ID for easy lookup
            vocab_ref.document(data['word_text']).set(data)

# --- 2. Fetching Quiz Data ---
def get_quiz_question():
    vocab_ref = db.collection("vocabulary_master")
    docs = list(vocab_ref.stream())
    
    if not docs:
        return None, []
        
    vocab_list = [doc.to_dict() for doc in docs]
    
    # Sort to find the weakest / most repeated word
    def sort_key(x):
        total = x.get('total_attempts', 0)
        success_rate = (x.get('correct_attempts', 0) / total) if total > 0 else 0
        return (success_rate, -x.get('repeat_count', 0))
        
    vocab_list.sort(key=sort_key)
    target_word = vocab_list[0]
    
    # Get 3 decoys from the same category
    same_category = [w['word_text'] for w in vocab_list if w['category'] == target_word['category'] and w['word_text'] != target_word['word_text']]
    decoys = random.sample(same_category, min(len(same_category), 3))
    
    while len(decoys) < 3:
        decoys.append("Placeholder Decoy")
        
    options = decoys + [target_word['word_text']]
    random.shuffle(options)
    
    return target_word, options

# --- 3. Update Performance ---
def update_score(word_text, is_correct):
    doc_ref = db.collection("vocabulary_master").document(word_text)
    
    # Using a transaction or simple get/set to increment
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        new_total = data.get('total_attempts', 0) + 1
        new_correct = data.get('correct_attempts', 0) + (1 if is_correct else 0)
        
        doc_ref.update({
            'total_attempts': new_total,
            'correct_attempts': new_correct
        })

# --- 4. Streamlit UI ---
st.set_page_config(page_title="SSC CGL Vocab Tracker", layout="centered")
init_db()

st.title("📚 SSC CGL Tracker - Target: May 31")

menu = st.sidebar.selectbox("Navigation", ["Daily Quiz", "Progress Dashboard"])

if menu == "Daily Quiz":
    st.header("Adaptive Vocabulary Quiz")
    
    if 'current_q' not in st.session_state:
        st.session_state.current_q, st.session_state.options = get_quiz_question()
        st.session_state.answered = False

    if st.session_state.current_q:
        q_data = st.session_state.current_q
        
        st.markdown(f"**Category:** {q_data['category']}")
        st.subheader("What is the single word for:")
        st.info(f"*{q_data['definition']}*")
        
        with st.expander("Show Hindi Hint"):
            st.write(q_data.get('hindi_meaning', 'No hint available'))

        choice = st.radio("Select the correct word:", st.session_state.options, index=None, disabled=st.session_state.answered)
        
        if st.button("Submit Answer", disabled=st.session_state.answered):
            if choice:
                st.session_state.answered = True
                if choice == q_data['word_text']:
                    st.success(f"Correct! ✅")
                    update_score(q_data['word_text'], True)
                else:
                    st.error(f"Incorrect. ❌ The correct word was **{q_data['word_text']}**.")
                    update_score(q_data['word_text'], False)
                st.rerun()
            else:
                st.warning("Please select an option first.")
                
        if st.session_state.answered:
            if st.button("Next Question ➡️"):
                st.session_state.current_q, st.session_state.options = get_quiz_question()
                st.session_state.answered = False
                st.rerun()

elif menu == "Progress Dashboard":
    st.header("Your Mastery Metrics")
    docs = db.collection("vocabulary_master").stream()
    data = [doc.to_dict() for doc in docs]
    
    if data:
        df = pd.DataFrame(data)
        df['Success Rate (%)'] = (df['correct_attempts'] / df['total_attempts'].replace(0, 1)) * 100
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Words", len(df))
        col2.metric("High Priority (#R > 2)", len(df[df['repeat_count'] > 2]))
        col3.metric("Weak Words (< 50%)", len(df[(df['Success Rate (%)'] < 50) & (df['total_attempts'] > 0)]))
        
        st.dataframe(df[['word_text', 'category', 'repeat_count', 'Success Rate (%)']].sort_values(by='Success Rate (%)'))
    else:
        st.write("Database is empty.")