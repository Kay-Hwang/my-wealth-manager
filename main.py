import streamlit as st
import plotly.express as px

from input_ui import render_input_ui
from edit_ui import render_edit_ui
from data_module import load_all_trades
from calc_module import get_holdings_per_ticker, get_monthly_dividends, get_account_summary

# Streamlit 페이지 기본 설정 (와이드 모드)
st.set_page_config(page_title="개인 자산 포트폴리오 관리", page_icon="📈", layout="wide")

# 모바일 호환성을 위한 커스텀 CSS 주입
st.markdown("""
    <style>
    /* 모바일 환경에서 좌우 여백을 줄여 공간 확보 */
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 1.5rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    /* 카드 컨테이너 내부 글씨 크기 조정 */
    div[data-testid="stMarkdownContainer"] {
        font-size: 0.95rem;
    }
    </style>
""", unsafe_allow_html=True)

def render_dashboard():
    st.title("📊 포트폴리오 대시보드")
    
    # 데이터 로드
    df = load_all_trades()
    if df.empty:
        st.info("아직 기록된 거래 내역이 없습니다. 왼쪽 '거래 내역 입력' 메뉴에서 데이터를 추가해주세요!")
        return

    # 1. 상단: 모든 계좌 합산 총 자산 (하이라이트)
    account_df = get_account_summary(df)
    
    if not account_df.empty:
        total_krw = account_df['원화합계(KRW)'].sum()
        total_usd = account_df['달러합계(USD)'].sum()
        total_converted = account_df['총자산(KRW환산)'].sum()
        total_cost = account_df['총원금(KRW환산)'].sum()
        
        # 현재수익 (미실현)
        total_profit = total_converted - total_cost
        total_pct = (total_profit / total_cost * 100) if total_cost > 0 else 0.0
        
        # 누적수익 (미실현 + 실현 배당금)
        from calc_module import get_monthly_dividends
        div_df = get_monthly_dividends(df)
        total_div = div_df[div_df['구분'] == '수령완료']['배당금(KRW)'].sum() if not div_df.empty else 0.0
        
        accumulated_profit = total_profit + total_div
        accumulated_pct = (accumulated_profit / total_cost * 100) if total_cost > 0 else 0.0
        
        st.markdown("## 💰 나의 총 자산 및 수익")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("총 자산 (원화 환산)", f"₩ {int(total_converted):,}", f"{total_pct:+.2f}% (현재수익률)")
        with c2:
            st.metric("누적 수익금 (배당 포함)", f"₩ {int(accumulated_profit):,}", f"{accumulated_pct:+.2f}% (누적수익률)")
        with c3:
            st.metric("총 원화 자산 (KRW)", f"₩ {int(total_krw):,}")
        with c4:
            st.metric("총 달러 자산 (USD)", f"$ {total_usd:,.2f}")
            
        st.markdown("---")
        
        # 1-1. 중간: 계좌별 상세 현황
        st.subheader("💳 계좌별 상세 자산 현황")
        
        # 가로폭이 좁아져 길쭉해지는 것을 방지하기 위해 한 줄에 최대 3개까지만 배치
        num_cols = 3
        for i in range(0, len(account_df), num_cols):
            cols = st.columns(num_cols)
            for j in range(num_cols):
                if i + j < len(account_df):
                    row = account_df.iloc[i + j]
                    with cols[j]:
                        with st.container(border=True): # 예쁜 카드 형태의 테두리 위젯 렌더링
                            st.markdown(f"#### 📂 {row['계좌종류']}")
                            st.markdown(f"**총 자산: ₩ {int(row['총자산(KRW환산)']):,}**")
                            
                            # 수익률 텍스트 컬러 코딩
                            cur_sign = "+" if row['현재수익률(%)'] > 0 else ""
                            acc_sign = "+" if row['누적수익률(%)'] > 0 else ""
                            cur_col = "#00CC96" if row['현재수익률(%)'] > 0 else "#EF553B" if row['현재수익률(%)'] < 0 else "gray"
                            acc_col = "#00CC96" if row['누적수익률(%)'] > 0 else "#EF553B" if row['누적수익률(%)'] < 0 else "gray"
                            
                            st.markdown(f"<span style='color:{cur_col}'><b>현재 {cur_sign}{int(row['현재수익금(KRW환산)']):,}</b> ({cur_sign}{row['현재수익률(%)']:.2f}%)</span>", unsafe_allow_html=True)
                            st.markdown(f"<span style='color:{acc_col}'><b>누적 {acc_sign}{int(row['누적수익금(KRW환산)']):,}</b> ({acc_sign}{row['누적수익률(%)']:.2f}%)</span>", unsafe_allow_html=True)
                            
                            info_md = f"- 🇰🇷 **원화 자산 합계**: ₩ {int(row['원화합계(KRW)']):,}\n"
                            info_md += f"  - 주식: ₩ {int(row['주식자산(KRW)']):,}\n"
                            info_md += f"  - 예수금: ₩ {int(row['현금자산(KRW)']):,}\n"
                            info_md += f"- 🇺🇸 **달러 자산 합계**: $ {row['달러합계(USD)']:,.2f}\n"
                            info_md += f"  - 주식: $ {row['주식자산(USD)']:,.2f}\n"
                            info_md += f"  - 예수금: $ {row['현금자산(USD)']:,.2f}"
                            st.caption(info_md)
    else:
        st.write("관련 데이터가 없습니다.")

    st.markdown("---")
    
    # 2. 종목별 보유 현황 (표가 가로로 길어지므로 가장 위에 전폭으로 배치)
    st.subheader("📋 계좌 및 종목별 보유 현황")
    holdings_df = get_holdings_per_ticker(df)
    
    if not holdings_df.empty:
        st.dataframe(
            holdings_df,
            use_container_width=True,
            hide_index=True,
            column_order=["계좌종류", "자산분류", "티커", "종목명", "통화", "총보유수량", "평균매수단가", "적용현재가", "평가수익금(지역통화)", "현재수익률(%)"],
            column_config={
                "계좌종류": st.column_config.TextColumn("계좌", width="small"),
                "자산분류": st.column_config.TextColumn("분류", width="small"),
                "티커": st.column_config.TextColumn("종목코드", width="small"),
                "종목명": st.column_config.TextColumn("종목명", width="medium"),
                "통화": st.column_config.TextColumn("통화", width="small"),
                "총보유수량": st.column_config.NumberColumn("보유 주수", format="%.3f"),
                "평균매수단가": st.column_config.NumberColumn("평단가", format="%.2f"),
                "적용현재가": st.column_config.NumberColumn("현재가", format="%.2f"),
                "평가수익금(지역통화)": st.column_config.NumberColumn("수익금(현지통화)", format="%.2f"),
                "현재수익률(%)": st.column_config.NumberColumn("수익률(%)", format="%.2f %%")
            }
        )
    else:
        st.write("현재 보유 중인 종목이 없습니다.")

    st.markdown("---")
    
    # 3. 하단: 배당금 현황 (좌/우 분할)
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("📊 월별 배당금 현황")
        div_df = get_monthly_dividends(df)
        
        if not div_df.empty:
            div_df['텍스트'] = div_df['배당금(KRW)'].apply(lambda x: f"{x:,.0f}" if x > 0 else "")
            fig = px.bar(
                div_df, 
                x="연월", 
                y="배당금(KRW)", 
                color="구분",
                barmode="stack",
                color_discrete_map={"수령완료": "#00CC96", "수령예상": "#FFA15A"},
                labels={"배당금(KRW)": "배당금 총액 (원화)", "연월": "발생 월"},
                text="텍스트"
            )
            fig.update_traces(textposition='auto')
            fig.update_layout(
                xaxis_type='category',
                xaxis={'categoryorder': 'category ascending'},
                xaxis_tickangle=-45,
                margin=dict(l=0, r=0, t=30, b=0), # 모바일 꽉 차게
                legend=dict(orientation="h", yanchor="bottom", y=1.1, xanchor="center", x=0.5), # 범례를 위로
                font=dict(size=10) # 폰트 사이즈 조정
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("아직 배당 내역이 없습니다.")
            
    with col_chart2:
        st.subheader("📈 연도별 배당금 성장 추이")
        from calc_module import get_yearly_dividends
        year_df = get_yearly_dividends(df)
        
        if not year_df.empty:
            year_df['텍스트'] = year_df['배당금(KRW)'].apply(lambda x: f"{x:,.0f}" if x > 0 else "")
            fig2 = px.bar(
                year_df, 
                x="연도", 
                y="배당금(KRW)", 
                color="구분",
                barmode="stack",
                color_discrete_map={"수령완료": "#AB63FA", "수령예상": "#FFA15A"},
                labels={"배당금(KRW)": "누적 배당금 (원화)", "연도": "발생 연도"},
                text="텍스트"
            )
            fig2.update_traces(textposition='auto')
            
            # 기본적으로 x축 뼈대를 카테고리형으로 순서대로 띄움
            fig2.update_layout(
                xaxis_type='category',
                xaxis={'categoryorder': 'category ascending'},
                margin=dict(l=0, r=0, t=30, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.1, xanchor="center", x=0.5),
                font=dict(size=10)
            )
            
            # 카테고리가 5년(5개)을 초과할 경우 초기 화면을 5칸으로 잘라두고 하단에 스크롤(rangeslider) 바를 생성
            num_years = len(year_df['연도'].unique())
            if num_years > 5:
                fig2.update_layout(
                    xaxis=dict(
                        range=[-0.5, 4.5],  # 0번째~4번째까지만 화면에 노출 (5년어치)
                        rangeslider=dict(visible=True, thickness=0.1) # 하단에 드래그할 수 있는 스크롤러 장착!
                    )
                )
            
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("아직 데이터가 없습니다.")

    st.markdown("---")
    
    # 4. 가장 하단 : 종목별 배당금 상세
    st.subheader("📝 대상 종목별 배당금 청구서")
    
    from calc_module import get_dividends_by_ticker
    div_ticker_df = get_dividends_by_ticker(df)
    
    if not div_ticker_df.empty:
        st.dataframe(
            div_ticker_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "티커": st.column_config.TextColumn("종목코드", width="small"),
                "종목명": st.column_config.TextColumn("종목명", width="medium"),
                "올해수령액(KRW)": st.column_config.NumberColumn("올해 누적 배당금", format="₩ %.0f"),
                "전체누적수령액(KRW)": st.column_config.NumberColumn("투자 이후 총 배당금", format="₩ %.0f")
            }
        )
    else:
        st.info("아직 완료된 배당 수령 내역이 없습니다.")

def main():
    # 사이드바 메뉴 구성
    with st.sidebar:
        st.title("메뉴")
        st.markdown("원하는 메뉴를 선택하세요.")
        menu = st.radio("내비게이션", ["대시보드", "거래 내역 입력", "내역 전체 조회 및 수정"])
        
    # 분기
    if menu == "대시보드":
        render_dashboard()
    elif menu == "거래 내역 입력":
        render_input_ui()
    elif menu == "내역 전체 조회 및 수정":
        render_edit_ui()

if __name__ == "__main__":
    main()
