import streamlit as st
import yfinance as yf
import pandas as pd
from data_module import load_all_trades

@st.cache_data(ttl=600)  # 10분마다 갱신하여 딜레이 최소화
def get_live_info(tickers_tuple):
    """
    야후 파이낸스를 통해 넘어온 티커들의 최신 종가(현재가)와 공식 종목명을 가져옵니다.
    """
    prices = {}
    names = {}
    for txt in tickers_tuple:
        if txt == 'CASH': continue
        
        search_tickers = [txt]
        if txt.isdigit(): 
            search_tickers = [txt + ".KS", txt + ".KQ"] # 한국 종목 대응
        elif any('\uac00' <= char <= '\ud7a3' for char in txt):
            prices[txt] = None
            names[txt] = txt
            continue
            
        found = False
        for tick in search_tickers:
            try:
                t = yf.Ticker(tick)
                hist = t.history(period="1d")
                if not hist.empty:
                    prices[txt] = hist['Close'].values[-1]
                    # 오류가 잦은 info에서 이름을 가져오고, 없으면 입력한 거 그대로
                    name = t.info.get('shortName') or t.info.get('longName') or txt
                    names[txt] = name
                    found = True
                    break
            except Exception:
                pass
        
        if not found:
            prices[txt] = None
            names[txt] = txt
            
    return prices, names

def get_cash_balances_by_account(df=None):
    """
    각 계좌별로 KRW, USD 현금(예수금) 잔액을 계산하여 반환합니다.
    """
    if df is None:
        df = load_all_trades()
        
    if df.empty:
        return pd.DataFrame(columns=['계좌종류', '통화', '현금잔고'])
        
    calc_df = df.copy()
    calc_df['거래금액'] = calc_df['단가'] * calc_df['수량']
    
    # 자금의 유출입 계산 트리
    def get_cash_sign(trade_type):
        # 입금, 매도, 배당 -> 내 예수금이 늘어난다 (현금 증가)
        if trade_type in ['입금', '매도', '배당']:
            return 1
        # 출금, 매수 -> 내 예수금이 줄어든다 (현금 감소)
        elif trade_type in ['출금', '매수']:
            return -1
        else:
            return 0
            
    calc_df['현금증감'] = calc_df['거래종류'].apply(get_cash_sign) * calc_df['거래금액']
    
    cash_df = calc_df.groupby(['계좌종류', '통화'])['현금증감'].sum().reset_index()
    cash_df.rename(columns={'현금증감': '현금잔고'}, inplace=True)
    return cash_df

def get_holdings_per_ticker(df=None):
    """
    계좌별 + 종목별(티커별) 평균 매수 단가와 총 보유 수량을 계산합니다.
    (현금 항목 CASH는 제외한 순수 투자자산들 중심)
    """
    if df is None:
        df = load_all_trades()
        
    if df.empty:
        return pd.DataFrame(columns=['계좌종류', '티커', '총보유수량', '평균매수단가', '통화'])

    # CASH 항목 제거
    stocks_df = df[df['티커'] != 'CASH'].copy()
    if stocks_df.empty:
        return pd.DataFrame(columns=['계좌종류', '티커', '총보유수량', '평균매수단가', '통화'])

    # 단가 계산 (매수만 기준)
    buys = stocks_df[stocks_df['거래종류'] == '매수'].copy()
    if not buys.empty:
        buys['투자금액'] = buys['단가'] * buys['수량']
        ticker_buys = buys.groupby(['계좌종류', '티커'])[['수량', '투자금액']].sum().reset_index()
        # 평균매수단가 = 총 투자금액 / 총 수량
        ticker_buys['평균매수단가'] = ticker_buys['투자금액'] / ticker_buys['수량']
        avg_price = ticker_buys[['계좌종류', '티커', '평균매수단가']]
    else:
        avg_price = pd.DataFrame(columns=['계좌종류', '티커', '평균매수단가'])

    # 수량 증감 계산
    buy_qty = stocks_df[stocks_df['거래종류'] == '매수'].groupby(['계좌종류', '티커'])['수량'].sum().reset_index(name='매수수량')
    sell_qty = stocks_df[stocks_df['거래종류'] == '매도'].groupby(['계좌종류', '티커'])['수량'].sum().reset_index(name='매도수량')
    
    # 맵핑용 테이블 (통화, 환율 확인)
    currency_map = stocks_df.drop_duplicates(subset=['계좌종류', '티커'], keep='last')[['계좌종류', '티커', '통화', '적용환율', '자산분류']]
    all_tickers = stocks_df[['계좌종류', '티커']].drop_duplicates()
    
    qty_df = pd.merge(all_tickers, buy_qty, on=['계좌종류', '티커'], how='left').fillna(0)
    qty_df = pd.merge(qty_df, sell_qty, on=['계좌종류', '티커'], how='left').fillna(0)
    qty_df['총보유수량'] = qty_df['매수수량'] - qty_df['매도수량']
    
    result = pd.merge(qty_df[['계좌종류', '티커', '총보유수량']], avg_price, on=['계좌종류', '티커'], how='left')
    result = pd.merge(result, currency_map, on=['계좌종류', '티커'], how='left')
    result['평균매수단가'] = result['평균매수단가'].fillna(0)
    
    # ---------------- 현재가 및 종목명, 수익률 연동 ----------------
    result = result[result['총보유수량'] > 0].copy()
    unique_tickers = tuple(result['티커'].unique())
    live_prices, live_names = get_live_info(unique_tickers)
    
    result['현재가'] = result['티커'].apply(lambda x: live_prices.get(x, None))
    result['종목명'] = result['티커'].apply(lambda x: live_names.get(x, x))
    
    # 현재가가 비어있으면(조회 에러) 평단가로 대치 (수익금 0원 / 수익률 0%)
    result['적용현재가'] = result['현재가'].fillna(result['평균매수단가'])

    
    # 평가수익금 = (현재가 - 평단가) * 수량
    result['적용현재가'] = pd.to_numeric(result['적용현재가'], errors='coerce').fillna(pd.to_numeric(result['평균매수단가'], errors='coerce'))
    result['평균매수단가'] = pd.to_numeric(result['평균매수단가'], errors='coerce')
    result['평가수익금(지역통화)'] = (result['적용현재가'] - result['평균매수단가']) * pd.to_numeric(result['총보유수량'], errors='coerce')
    
    # 현재수익률(%)
    calc_rtn = ((result['적용현재가'] - result['평균매수단가']) / result['평균매수단가']) * 100
    result['현재수익률(%)'] = calc_rtn.where(result['평균매수단가'] > 0, 0.0).astype(float)
    
    return result

def get_account_summary(df=None):
    """
    각 계좌별 현금 잔고(KRW, USD 별도) 표기 및 주식 자산 가치를 통화별로 분리하여 원화 환산 총 자산을 구합니다.
    (입금을 깜빡하고 매수만 입력하여 예수금이 마이너스가 되는 것을 방지하기 위해 0으로 보정합니다)
    """
    if df is None:
        df = load_all_trades()
        
    if df.empty:
        return pd.DataFrame(columns=['계좌종류', '주식자산(KRW)', '주식자산(USD)', '현금자산(KRW)', '현금자산(USD)', '총자산(KRW환산)'])

    # 1. 예수금 (현금 잔액 조회)
    cash_df = get_cash_balances_by_account(df)
    usd_rates = df[df['통화'] == 'USD']['적용환율']
    latest_usd_rate = usd_rates.iloc[-1] if not usd_rates.empty else 1400.0

    acct_cash = []
    accounts = df['계좌종류'].unique()
    for acct in accounts:
        acct_rows = cash_df[cash_df['계좌종류'] == acct]
        krw_cash = acct_rows[acct_rows['통화'] == 'KRW']['현금잔고'].sum()
        usd_cash = acct_rows[acct_rows['통화'] == 'USD']['현금잔고'].sum()
        
        # [핵심] 입금을 깜빡하고 주식만 '매수' 기록했을 때 예수금이 음수로 빠져 원금이 0이 되는 현상 방어
        if krw_cash < 0: krw_cash = 0
        if usd_cash < 0: usd_cash = 0
        
        krw_converted = krw_cash + (usd_cash * latest_usd_rate)
        acct_cash.append({
            '계좌종류': acct, 
            '현금자산(KRW)': krw_cash, 
            '현금자산(USD)': usd_cash, 
            '예수금합계(KRW환산)': krw_converted
        })
    cash_summary = pd.DataFrame(acct_cash)

    # 2. 투자 주식 자산 (달러/원화 분리 계산)
    holdings = get_holdings_per_ticker(df)
    if not holdings.empty:
        # 적용현재가 기준으로 현재 가치 평가
        holdings['주식가치_원음'] = holdings['총보유수량'] * holdings['적용현재가']
        # 평균매수단가 기준으로 투자 원금 계산
        holdings['투자원금_원음'] = holdings['총보유수량'] * holdings['평균매수단가']
        
        # 원화 주식 분리
        krw_mask = holdings['통화'] == 'KRW'
        krw_stocks = holdings[krw_mask].groupby('계좌종류')['주식가치_원음'].sum().reset_index()
        krw_stocks.rename(columns={'주식가치_원음': '주식자산(KRW)'}, inplace=True)
        krw_cost = holdings[krw_mask].groupby('계좌종류')['투자원금_원음'].sum().reset_index()
        krw_cost.rename(columns={'투자원금_원음': '주식원금(KRW)'}, inplace=True)
        
        # 달러 주식 분리
        usd_mask = holdings['통화'] == 'USD'
        usd_stocks = holdings[usd_mask].groupby('계좌종류')['주식가치_원음'].sum().reset_index()
        usd_stocks.rename(columns={'주식가치_원음': '주식자산(USD)'}, inplace=True)
        usd_cost = holdings[usd_mask].groupby('계좌종류')['투자원금_원음'].sum().reset_index()
        usd_cost.rename(columns={'투자원금_원음': '주식원금(USD)'}, inplace=True)
        
        stock_value = pd.merge(pd.DataFrame({'계좌종류': accounts}), krw_stocks, on='계좌종류', how='left').fillna(0)
        stock_value = pd.merge(stock_value, krw_cost, on='계좌종류', how='left').fillna(0)
        stock_value = pd.merge(stock_value, usd_stocks, on='계좌종류', how='left').fillna(0)
        stock_value = pd.merge(stock_value, usd_cost, on='계좌종류', how='left').fillna(0)
    else:
        stock_value = pd.DataFrame({
            '계좌종류': accounts, 
            '주식자산(KRW)': 0.0, 
            '주식자산(USD)': 0.0,
            '주식원금(KRW)': 0.0,
            '주식원금(USD)': 0.0
        })

    # 3. 합치기 및 통화별 총계 도출
    result = pd.merge(cash_summary, stock_value, on='계좌종류', how='left').fillna(0)
    
    result['달러합계(USD)'] = result['현금자산(USD)'] + result['주식자산(USD)']
    result['달러원금(USD)'] = result['현금자산(USD)'] + result['주식원금(USD)']
    
    result['원화합계(KRW)'] = result['현금자산(KRW)'] + result['주식자산(KRW)']
    result['원화원금(KRW)'] = result['현금자산(KRW)'] + result['주식원금(KRW)']
    
    result['총자산(KRW환산)'] = result['원화합계(KRW)'] + (result['달러합계(USD)'] * latest_usd_rate)
    result['총원금(KRW환산)'] = result['원화원금(KRW)'] + (result['달러원금(USD)'] * latest_usd_rate)
    
    # 4. 배당 성과 계좌별 부착 (누적 수익률 용도)
    div_df = df[df['거래종류'] == '배당'].copy()
    if not div_df.empty:
        div_df['배당금(KRW)'] = div_df['단가'] * div_df['수량']
        div_df.loc[div_df['통화'] == 'USD', '배당금(KRW)'] *= latest_usd_rate
        
        div_df['DateObj'] = pd.to_datetime(div_df['날짜'], errors='coerce')
        today = pd.Timestamp.now().normalize()
        div_received = div_df[div_df['DateObj'] <= today]
        
        acct_div = div_received.groupby('계좌종류')['배당금(KRW)'].sum().reset_index()
        acct_div.rename(columns={'배당금(KRW)': '누적배당금(KRW)'}, inplace=True)
        result = pd.merge(result, acct_div, on='계좌종류', how='left').fillna(0)
    else:
        result['누적배당금(KRW)'] = 0.0
        
    # 5. 수익률 최종 도출
    result['현재수익금(KRW환산)'] = pd.to_numeric(result['총자산(KRW환산)'], errors='coerce') - pd.to_numeric(result['총원금(KRW환산)'], errors='coerce')
    
    calc_curr = (result['현재수익금(KRW환산)'] / pd.to_numeric(result['총원금(KRW환산)'], errors='coerce')) * 100
    result['현재수익률(%)'] = calc_curr.where(result['총원금(KRW환산)'] > 0, 0.0).astype(float)
    
    result['누적수익금(KRW환산)'] = result['현재수익금(KRW환산)'] + pd.to_numeric(result['누적배당금(KRW)'], errors='coerce')
    
    calc_cum = (result['누적수익금(KRW환산)'] / pd.to_numeric(result['총원금(KRW환산)'], errors='coerce')) * 100
    result['누적수익률(%)'] = calc_cum.where(result['총원금(KRW환산)'] > 0, 0.0).astype(float)
    
    result = result.sort_values(by='총자산(KRW환산)', ascending=False).reset_index(drop=True)
    return result

def get_asset_class_weight(df=None):
    """
    모든 주식/자산 평가금액 및 보유 중인 총 예수금(현금)을 통합하여 자산분류별 비중을 계산합니다.
    """
    if df is None:
        df = load_all_trades()
        
    if df.empty:
        return pd.DataFrame(columns=['자산분류', '평가금액(KRW기준)', '비중(%)'])
        
    holdings = get_holdings_per_ticker(df)
    if not holdings.empty:
        holdings['평가금액'] = holdings['총보유수량'] * holdings['평균매수단가']
        usd_mask = holdings['통화'] == 'USD'
        holdings.loc[usd_mask, '평가금액'] *= holdings.loc[usd_mask, '적용환율']
        
        # 합계 계산
        stock_value = holdings.groupby('자산분류')['평가금액'].sum().reset_index()
    else:
        stock_value = pd.DataFrame(columns=['자산분류', '평가금액'])

    # 현금 자산을 "예수금(현금)" 항목으로 편입시킴
    acct_summary = get_account_summary(df)
    total_cash_value = acct_summary['현금가치(KRW환산)'].sum() if not acct_summary.empty else 0

    if total_cash_value > 0:
        cash_row = pd.DataFrame([{'자산분류': '예수금(현금)', '평가금액': total_cash_value}])
        result = pd.concat([stock_value, cash_row], ignore_index=True)
    else:
        result = stock_value
        
    result.rename(columns={'평가금액': '평가금액(KRW기준)'}, inplace=True)
    total_invested = result['평가금액(KRW기준)'].sum()
    
    if total_invested > 0:
        result['비중(%)'] = (result['평가금액(KRW기준)'] / total_invested) * 100
        result['비중(%)'] = result['비중(%)'].round(2)
    else:
        result['비중(%)'] = 0.0
        
    result = result.sort_values(by='비중(%)', ascending=False).reset_index(drop=True)
    return result

def get_monthly_dividends(df=None):
    """
    거래종류가 '배당'인 내역을 대상으로 월별 누적 배당금(원화 환산)을 계산합니다.
    1월부터 12월까지 빈 포맷이라도 항상 나오도록 DataFrame을 미리 구성합니다.
    """
    if df is None:
        df = load_all_trades()
        
    current_year = pd.Timestamp.now().year
    
    # 당해 년도의 1월~12월 뼈대
    def make_empty_months(year):
        return [f"{year}-{str(m).zfill(2)}" for m in range(1, 13)]
        
    if df.empty:
        return pd.DataFrame({'연월': make_empty_months(current_year), '배당금(KRW)': 0.0, '구분': '수령완료'})
        
    div_df = df[df['거래종류'] == '배당'].copy()
    if div_df.empty:
        return pd.DataFrame({'연월': make_empty_months(current_year), '배당금(KRW)': 0.0, '구분': '수령완료'})
        
    div_df['배당금(KRW)'] = div_df['단가'] * div_df['수량']
    exchange_rate = 1400.0 
    div_df.loc[div_df['통화'] == 'USD', '배당금(KRW)'] *= exchange_rate
    
    div_df['DateObj'] = pd.to_datetime(div_df['날짜'], errors='coerce')
    div_df = div_df.dropna(subset=['DateObj'])
    
    today = pd.Timestamp.now().normalize()
    div_df['구분'] = div_df['DateObj'].apply(lambda d: '수령완료' if d <= today else '수령예상')
    div_df['연월'] = div_df['DateObj'].dt.strftime('%Y-%m')
    
    monthly_div = div_df.groupby(['연월', '구분'])['배당금(KRW)'].sum().reset_index()
    
    # 데이터에 존재하는 년도들에 대해 1~12월 뼈대를 모두 만듦 (최소한 금년도 포함)
    years_in_data = div_df['DateObj'].dt.year.unique()
    all_years = set([current_year]) | set(years_in_data)
    
    expanded_months = []
    for y in sorted(list(all_years)):
        expanded_months.extend(make_empty_months(y))
            
    base_df = pd.DataFrame({'연월': expanded_months})
    
    # 실제 배당금 기록과 뼈대를 병합
    merged = pd.merge(base_df, monthly_div, on='연월', how='left')
    merged['배당금(KRW)'] = merged['배당금(KRW)'].fillna(0.0)
    
    # 빈 값인 행의 구분을 현재 날짜 기준으로 채워줌 (에러 방지 및 색상 통일)
    current_month_str = today.strftime('%Y-%m')
    def fill_type(row):
        if pd.isna(row['구분']):
            return '수령완료' if row['연월'] < current_month_str else '수령예상'
        return row['구분']
        
    merged['구분'] = merged.apply(fill_type, axis=1)
    
    # 정렬하여 반환
    merged = merged.sort_values(by=['연월', '구분'])
    return merged

def get_yearly_dividends(df=None):
    """
    거래종류가 '배당'인 내역을 대상으로 연도별 누적 배당금을 계산합니다.
    """
    if df is None:
        df = load_all_trades()
        
    current_year = pd.Timestamp.now().year
    
    if df.empty:
        five_years = [str(current_year + i) for i in range(5)]
        return pd.DataFrame({'연도': five_years, '배당금(KRW)': 0.0, '구분': '수령완료'})
        
    div_df = df[df['거래종류'] == '배당'].copy()
    if div_df.empty:
        five_years = [str(current_year + i) for i in range(5)]
        return pd.DataFrame({'연도': five_years, '배당금(KRW)': 0.0, '구분': '수령완료'})
        
    div_df['배당금(KRW)'] = div_df['단가'] * div_df['수량']
    # USD인 경우 임시 고정환율 적용
    exchange_rate = 1400.0 
    div_df.loc[div_df['통화'] == 'USD', '배당금(KRW)'] *= exchange_rate
    
    div_df['DateObj'] = pd.to_datetime(div_df['날짜'], errors='coerce')
    div_df = div_df.dropna(subset=['DateObj'])
    
    today = pd.Timestamp.now().normalize()
    div_df['구분'] = div_df['DateObj'].apply(lambda d: '수령완료' if d <= today else '수령예상')
    div_df['연도'] = div_df['DateObj'].dt.strftime('%Y')
    
    yearly_div = div_df.groupby(['연도', '구분'])['배당금(KRW)'].sum().reset_index()
    
    # 올해부터 5년간의 뼈대를 무조건 보장
    years_in_data = div_df['DateObj'].dt.year.unique()
    all_years = set([current_year + i for i in range(5)]) | set(years_in_data)
    
    base_df = pd.DataFrame({'연도': [str(y) for y in sorted(list(all_years))]})
    
    merged = pd.merge(base_df, yearly_div, on='연도', how='left')
    merged['배당금(KRW)'] = merged['배당금(KRW)'].fillna(0.0)
    
    current_year_str = str(current_year)
    def fill_type(row):
        if pd.isna(row['구분']):
            return '수령완료' if row['연도'] < current_year_str else '수령예상'
        return row['구분']
        
    merged['구분'] = merged.apply(fill_type, axis=1)
    merged = merged.sort_values(by=['연도', '구분'])
    
    return merged

def get_dividends_by_ticker(df=None):
    """
    각 종목(티커) 단위로 누적 배당수령액과 예상수령액의 합계를 구합니다.
    """
    if df is None:
        df = load_all_trades()
        
    div_df = df[df['거래종류'] == '배당'].copy()
    if div_df.empty:
        return pd.DataFrame(columns=['티커', '종목명', '올해수령액(KRW)', '전체누적수령액(KRW)'])
        
    div_df['배당금(KRW)'] = div_df['단가'] * div_df['수량']
    exchange_rate = 1400.0 
    div_df.loc[div_df['통화'] == 'USD', '배당금(KRW)'] *= exchange_rate
    
    div_df['DateObj'] = pd.to_datetime(div_df['날짜'], errors='coerce')
    div_df = div_df.dropna(subset=['DateObj'])
    today = pd.Timestamp.now().normalize()
    
    # "다가올 배당(예상)"은 제외하고 수령 완료된 배당금만 취합
    div_df = div_df[div_df['DateObj'] <= today]
    
    if div_df.empty:
        return pd.DataFrame(columns=['티커', '종목명', '올해수령액(KRW)', '전체누적수령액(KRW)'])
        
    current_year = today.year
    div_df['올해여부'] = div_df['DateObj'].dt.year == current_year
    
    # 종목명 실시간 맵핑
    live_prices, live_names = get_live_info(tuple(div_df['티커'].unique()))
    div_df['종목명'] = div_df['티커'].apply(lambda x: live_names.get(x, x))
    
    # 종목별로 합산
    grouped = div_df.groupby(['티커', '종목명'])
    
    res = []
    for (ticker, name), group in grouped:
        total = group['배당금(KRW)'].sum()
        this_year = group[group['올해여부']]['배당금(KRW)'].sum()
        res.append({
            '티커': ticker,
            '종목명': name,
            '올해수령액(KRW)': this_year,
            '전체누적수령액(KRW)': total
        })
        
    pivot_div = pd.DataFrame(res)
    pivot_div = pivot_div.sort_values(by='전체누적수령액(KRW)', ascending=False).reset_index(drop=True)
    return pivot_div

