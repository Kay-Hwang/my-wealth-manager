import streamlit as st
import datetime
from data_module import add_trade

def render_input_ui():
    """사용자로부터 거래 내역을 수기로 입력받는 Streamlit UI 컴포넌트입니다."""
    st.subheader("✍️ 새로운 거래 내역 추가")
    
    # clear_on_submit=True 설정 시 제출 후 폼이 자동으로 초기화됩니다.
    with st.form("trade_input_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            date = st.date_input("날짜", value=datetime.date.today())
            trade_type = st.selectbox("거래종류", ["매수", "매도", "배당", "입금", "출금"])
            ticker = st.text_input("티커 (입출금 시 비워둬도 됨)").strip().upper()
            price = st.number_input("단가 혹은 총액", min_value=0.0, step=100.0, help="주식은 단가, 현금 입출금일 경우 금액 전체를 입력하세요.")
            
        with col2:
            quantity = st.number_input("수량", min_value=0.0, step=1.0, help="주식 수량. 입출금 시에는 1로 두셔도 됩니다.")
            currency = st.selectbox("통화 (결제수단)", ["KRW", "USD"])
            account_type = st.selectbox("계좌종류", ["미국직투계좌", "CMA", "IRP", "연금계좌", "퇴직연금계좌"])
            asset_cls = st.selectbox("자산분류", ["미국 배당 성장주", "국내주식", "현금", "배당금", "기타"])
            
        submitted = st.form_submit_button("저장하기", use_container_width=True)
        
        if submitted:
            date_str = date.strftime("%Y-%m-%d")
            # 입력값이 없다면 현금으로 간주
            ticker_val = ticker if ticker else "CASH"
            
            # 사용자 피드백: "적용환율 입력칸 제거, 알아서 적겠다"
            # 데이터 파일 구조(CSV)에는 낡은 오류를 뱉지 않도록 통일성을 위해 내부적으로만 1.0(또는 임의값)을 넘기도록 수정
            exchange_rate = 1400.0  # 나중에 실시간 API용으로 교체할 수 있는 변수 확보 
            
            # 수량을 입력하지 않았을 경우(0.0) 총액을 단가로 입력한 것으로 간주하여 1을 곱견줌
            final_quantity = quantity if quantity > 0 else 1.0
            
            # 1. 입금 / 출금 (예수금, 환전 용도)
            if trade_type in ["입금", "출금"]:
                add_trade(date_str, ticker_val, trade_type, price, final_quantity, currency, exchange_rate, account_type, asset_cls)
                st.success(f"✅ {date_str} 기준 {currency} {price * final_quantity} {trade_type} 내역이 안전하게 기록되었습니다!")
                
            # 2. 일반 거래 (매수, 매도, 배당)
            else:
                if not ticker:
                    st.error("🚨 주식/자산 거래 시에는 티커(종목코드)를 필수로 입력해주세요.")
                else:
                    add_trade(date_str, ticker_val, trade_type, price, final_quantity, currency, exchange_rate, account_type, asset_cls)
                    st.success(f"✅ {date_str} 기준 {ticker_val}의 {trade_type} 내역이 저장되었습니다!")
