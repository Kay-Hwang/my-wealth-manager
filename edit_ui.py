import streamlit as st
from data_module import load_all_trades, save_all_trades

def render_edit_ui():
    st.title("✏️ 거래 내역 조회 및 수정")
    st.markdown("과거에 입력한 데이터를 직접 수정하거나, 잘못된 내역을 삭제할 수 있습니다.")
    
    df = load_all_trades()
    
    if df.empty:
        st.info("아직 기록된 거래 내역이 없습니다.")
        return
        
    st.write("엑셀처럼 표의 칸을 더블클릭하여 값을 수정하거나, 행 선택 후 키보드 `Delete`로 삭제할 수 있습니다. 수정을 마치면 아래 '변경사항 저장' 버튼을 눌러주세요.")
    
    # st.data_editor 기능 사용 (삭제/추가/수정 모두 허용)
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="data_editor"
    )
    
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("💾 변경사항 저장", use_container_width=True):
            save_all_trades(edited_df)
            st.success("✅ 모든 변경사항이 안전하게 저장되었습니다!")
            st.balloons()
