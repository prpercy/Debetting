# Libraries
import streamlit as st
import pandas as pd
import argparse
from colorama import Fore, Style
from Utils.tools import get_json_data, to_data_frame, payout
from Utils.Dictionaries import team_index_current, sportsbook_index
from OddsProvider.SbrOddsProvider import SbrOddsProvider
import os
import json
from web3 import Web3
from pathlib import Path
from dotenv import load_dotenv
from streamlit.components.v1 import html


# Layout
st.set_page_config(page_title='NBA Odds and Bets', page_icon=':bar_chart:', layout='wide')
st.title('🌍 NBA Odds and Bets')

def nav_page(page_name, timeout_secs=5):
    nav_script = """
        <script type="text/javascript">
            function attempt_nav_page(page_name, start_time, timeout_secs) {
                var links = window.parent.document.getElementsByTagName("a");
                for (var i = 0; i < links.length; i++) {
                    if (links[i].href.toLowerCase().endsWith("/" + page_name.toLowerCase())) {
                        links[i].click();
                        return;
                    }
                }
                var elasped = new Date() - start_time;
                if (elasped < timeout_secs * 1000) {
                    setTimeout(attempt_nav_page, 100, page_name, start_time, timeout_secs);
                } else {
                    alert("Unable to navigate to page '" + page_name + "' after " + timeout_secs + " second(s).");
                }
            }
            window.addEventListener("load", function() {
                attempt_nav_page("%s", new Date(), %d);
            });
        </script>
    """ % (page_name, timeout_secs)
    html(nav_script)
    


if 'user_account_addr' not in st.session_state or st.session_state['user_account_addr'] == "":
    st.session_state['user_account_addr'] = ""
    st.warning("User has not registered or logged in. Please do so before you start betting", icon="⚠️")
    nav_page("Account")
    

st.write("\n")
st.caption(f"💳: {st.session_state.user_account_addr} ")

WEI_FACTOR = 10**18
SCORE_SCALING=100

# environment Variables
load_dotenv("./blockwager.env")

# Define and connect a new Web3 provider
w3 = Web3(Web3.HTTPProvider(os.getenv("WEB3_PROVIDER_URI")))

################################################################################
# Contract Helper function:
################################################################################

@st.cache(allow_output_mutation=True)
def load_contract():

    # Load the contract ABI
    with open(Path('./contracts/compiled/cbet_abi.json')) as f:
        artwork_abi = json.load(f)

    contract_address = os.getenv("SMART_CONTRACT_ADDRESS")
    
    # Load the contract
    contract = w3.eth.contract(
        address=contract_address,
        abi=artwork_abi
    )

    return contract

contract = load_contract()

st.session_state.user_balance_wallet_ether = w3.eth.getBalance(st.session_state.user_account_addr)
st.session_state.user_balance_wallet_token = contract.functions.balanceCbetTokens(st.session_state.user_account_addr).call()
(st.session_state.user_balance_betting_ether, st.session_state.user_balance_betting_token) = contract.functions.getBalanceUserBetting(st.session_state.user_account_addr).call()
(st.session_state.user_balance_escrow_ether, st.session_state.user_balance_escrow_token) = contract.functions.getBalanceUserEscrow(st.session_state.user_account_addr).call()
with st.expander("User account balances", expanded=True):
    c1, c2, c3, c4 = st.columns([2,2,2,2])
    with c1:
        st.info('**User Wallet Balance Ether**')
        st.info('**User Betting Balance Ether**')
    with c2:
        st.info(format(st.session_state.user_balance_wallet_ether/WEI_FACTOR,'.2f'))
        st.info(format(st.session_state.user_balance_betting_ether/WEI_FACTOR,'.2f'))
    with c3:
        st.info('**User Wallet Balance token**')
        st.info('**User Betting Balance token**')
    with c4:
        st.info(format(st.session_state.user_balance_wallet_token/WEI_FACTOR,'.2f'))
        st.info(format(st.session_state.user_balance_betting_token/WEI_FACTOR,'.2f'))
        
todays_games_url = os.getenv("NBA_GAME_URL")

data_url = os.getenv("NBA_DATA_URL")


# Style
with open('style.css')as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html = True)

#Sportsbook list
sportsbooks = ['fanduel', 'draftkings', 'betmgm', 'pointsbet', 'caesars', 'wynn', 'bet_rivers_ny']



class Bet:
    def __init__(self, sportsbook, game, team, bet_type, odds, spread, total, isOver):
        self.sportsbook = sportsbook
        self.game = game
        self.team = team
        self.bet_type = bet_type
        self.odds = odds
        self.amount=0
        self.spread=spread
        self.total=total*SCORE_SCALING
        self.isOver=isOver
        self.isEther=True
    def update_bet(self, amount,ccy):
        self.amount = w3.toWei(amount, "ether")
        if ccy == 'ETHER':
            self.isEther = True
        else:
            self.isEther = False

    
# Data Sources
@st.cache(ttl=600)
def getOdds(sportsbook):
    odds = None
    if sportsbooks != None:
        dict_games = SbrOddsProvider(sportsbook).get_odds()
    else:
        st.warning('Please select sportsbook', icon="⚠️")

    data = get_json_data(data_url)
    df = to_data_frame(data)
    return df, dict_games

if 'user_bets' not in st.session_state:
    st.session_state['user_bets'] = []
    
if 'user_dealing_ccy' not in st.session_state:
    st.session_state['user_dealing_ccy'] = "ETHER"
    
def add_bet(sportsbook, game, team, bet_type, odds, spread, total, isOver):
    if odds != "":
        st.session_state.user_bets.append(Bet(sportsbook, game, team, bet_type, odds, spread, total, isOver))
        
def place_bets():
    with st.expander("🟢 Bets placed", expanded=True):
        isError = False
        counter = 1
        for bet in st.session_state.user_bets:
            if f"bet_amount_{bet}" in st.session_state:
                if st.session_state[f'bet_amount_{bet}'] > 0:
                    try:
                        bet.update_bet(st.session_state[f'bet_amount_{bet}'], st.session_state.user_dealing_ccy)

                        isEther = (st.session_state.user_dealing_ccy == 'ETHER')
                        if bet.bet_type == 'ML':
                            contract.functions.createMoneylineBet(counter, sportsbook_index[bet.sportsbook], team_index_current[bet.team], bet.odds, 
                                            st.session_state.user_account_addr, bet.amount, isEther
                            ).transact({'from': st.session_state.cbet_account_owner_addr, 'gas': 1000000})
                        elif bet.bet_type == 'Spread':
                            contract.functions.createSpreadBet(counter, sportsbook_index[bet.sportsbook], team_index_current[bet.team], bet.odds, int(bet.spread), 
                                         st.session_state.user_account_addr, bet.amount, isEther
                            ).transact({'from': st.session_state.cbet_account_owner_addr, 'gas': 1000000})
                        elif bet.bet_type == 'Total':
                            contract.functions.createTotalBet(counter, sportsbook_index[bet.sportsbook], team_index_current[bet.team], bet.odds, bet.isOver, int(bet.total),
                                        st.session_state.user_account_addr, bet.amount, isEther
                            ).transact({'from': st.session_state.cbet_account_owner_addr, 'gas': 1000000})
                        counter = counter + 1
                    except Exception as ex:
                        isError = True
                        st.exception(ex.args[0]['message'])
                    if isError != True:    
                        with st.container():
                            c1, c2, c3 = st.columns(3)
                            with c1:
                                if bet.bet_type == 'ML':
                                    st.write(bet.team)
                                elif bet.bet_type == 'Spread':
                                    st.write(f"{bet.team} {bet.spread}")
                                elif bet.bet_type == 'Total':
                                    if bet.isOver:
                                        st.write(f"Over {bet.total/SCORE_SCALING}")
                                    else:
                                        st.write(f"Under {bet.total/SCORE_SCALING}")
                                st.caption(bet.bet_type)
                                st.caption(bet.game)
                            with c2:
                                st.write(f"**{bet.odds}**")
                                st.caption(f"@{bet.sportsbook}")
                            with c3:
                                st.info(f"{bet.amount/WEI_FACTOR} {st.session_state.user_dealing_ccy}")
                                st.info(f"Payout : {format(payout(bet.amount/WEI_FACTOR,bet.odds),'.2f')}")
                        st.write("---")

 
        st.session_state['user_bets'] = []
        if isError != True:
            st.success("✅Above bets were placed successfully.")
   


# Filter the sportsbooks
options = st.sidebar.multiselect(
    '**Select your desired sportsbook(s):**',
    options=sportsbooks,
    default='fanduel',
    key='sportsbook_options'
)
# Present Odds to Client
if len(options) == 0:
    st.warning('Please select at least one sportsbook.', icon="⚠️")
else:
    dict_game_options = {}
    dict_df = {}
    st.sidebar.write('---')
    for i in range(len(options)):
        sportsbook = options[i]
        df, dict_games = getOdds(sportsbook)
        df1 = pd.DataFrame.from_dict(dict_games).T

        #Team list
        games = df1['game'].unique()


        # Filter for teams
        game_options = st.sidebar.multiselect(
            f'**Select your matches(s) for sportsbook {sportsbook}:**',
            options=games,
            default=games[1],
            key= f'game_options_{sportsbook}'
        )
        dict_game_options.update({sportsbook : game_options})
        dict_df.update({sportsbook : df1})

    with st.container():
        c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([2,4,3,3,3,2,3,3])
        with c1:
            st.write("")
        with c2:
            st.success("Team")
        with c3:
            st.success("Moneyline")
        with c4:
            st.success("Spread")
        with c5:
            st.success("Total")
        with c6:
            st.success("Bets")
        with c7:
            st.button(label='Place bets', key="place_bets", on_click=place_bets)
        with c8:
            asset_type_lst = ["ETHER", "CBET TOKENS"]
            asset_type = st.selectbox('Select Asset Type', asset_type_lst, label_visibility="collapsed", key="user_dealing_ccy")
    counter = 0
    isExpanded = True
    for sportsbook in dict_game_options:
        game_options = dict_game_options[sportsbook]
        df1 = dict_df[sportsbook]
        #st.caption(f"**:blue[_Overview for {sportsbook}_]**")
        with st.expander(f"Overview for {sportsbook}", isExpanded):
            idx = 1
            for game in game_options:
                df2 = df1[df1['game']==game]
                counter = df1[df1['game']==game].index.values[0]
                #st.subheader(df2.game[counter])
                st.caption(df2.game[counter])
                with st.container():
                    c1, c2, c3,c4, c5, c6, c7, c8 = st.columns([2,4,3,3,3,2,3,3])
                    with c1:
                        st.info("Home", icon="⬛️")
                    with c2:
                        st.info(f"{df2.home_team[counter]}")
                    with c3:
                        st.button(
                            f"{df2.home_ml_odds[counter]}", 
                            key=f"{sportsbook}_{df2.home_team[counter]}_ml_{counter}", 
                            on_click=add_bet, 
                            args=(sportsbook,df2.game[counter],df2.home_team[counter],"ML",df2.home_ml_odds[counter],0, 0, False, )
                        )
                    with c4:
                        st.button(
                            f"{df2.home_spread[counter]}    {df2.home_spread_odds[counter]}", 
                            key=f"{sportsbook}_{df2.home_team[counter]}_s_{counter}",
                            on_click=add_bet, 
                            args=(sportsbook,df2.game[counter],df2.home_team[counter],"Spread",df2.home_spread_odds[counter],df2.home_spread[counter], 0, False, )
                        )
                    with c5:
                        st.button(
                            f"O: {df2.home_total[counter]}    {df2.over_odds[counter]}", 
                            key=f"{sportsbook}_{df2.home_team[counter]}_t_{counter}",
                            on_click=add_bet, 
                            args=(sportsbook,df2.game[counter],df2.home_team[counter],"Total",df2.over_odds[counter], 0, df2.home_total[counter], True,)
                        )
                    with c6:
                        for bet in st.session_state.user_bets:
                            if (bet.game  == df2.game[counter] and bet.sportsbook == sportsbook and bet.team == df2.home_team[counter]):
                                st.info(bet.bet_type)
                    with c7:
                        for bet in st.session_state.user_bets:
                            if (bet.game  == df2.game[counter] and bet.sportsbook == sportsbook and bet.team == df2.home_team[counter]):
                                st.number_input("amount",key=f"bet_amount_{bet}", label_visibility="collapsed")
                    with c8:
                        for bet in st.session_state.user_bets:
                            if (bet.game  == df2.game[counter] and bet.sportsbook == sportsbook and bet.team == df2.home_team[counter]):
                                st.info(f"Payout : {format(payout(st.session_state[f'bet_amount_{bet}'],bet.odds),'.2f')}")

                with st.container():
                    c1, c2, c3,c4, c5, c6, c7, c8 = st.columns([2,4,3,3,3,2,3,3])
                    with c1:
                        st.info("Away", icon="🟥")
                    with c2:
                        st.info(f"{df2.away_team[counter]}")
                    with c3:
                        st.button(
                            f"{df2.away_ml_odds[counter]}", 
                            key=f"{sportsbook}_{df2.away_team[counter]}_ml_{counter}",
                            on_click=add_bet, 
                            args=(sportsbook,df2.game[counter],df2.away_team[counter],"ML",df2.away_ml_odds[counter], 0, 0, False,)
                        )
                    with c4:
                        st.button(
                            f"{df2.away_spread[counter]}    {df2.away_spread_odds[counter]}", 
                            key=f"{sportsbook}_{df2.away_team[counter]}_s_{counter}",
                            on_click=add_bet, 
                            args=(sportsbook,df2.game[counter],df2.away_team[counter],"Spread",df2.away_spread_odds[counter], df2.away_spread[counter], 0, False,)
                        )
                    with c5:
                        st.button(
                            f"U: {df2.away_total[counter]}    {df2.under_odds[counter]}", 
                            key=f"{sportsbook}_{df2.away_team[counter]}_t_{counter}",
                            on_click=add_bet, 
                            args=(sportsbook,df2.game[counter],df2.away_team[counter],"Total",df2.under_odds[counter],0, df2.away_total[counter], False, )
                        )
                    with c6:
                        for bet in st.session_state.user_bets:
                            if (bet.game  == df2.game[counter] and bet.sportsbook == sportsbook and bet.team == df2.away_team[counter]):
                                st.info(bet.bet_type)
                    with c7:
                        for bet in st.session_state.user_bets:
                            if (bet.game  == df2.game[counter] and bet.sportsbook == sportsbook and bet.team == df2.away_team[counter]):
                                st.number_input("amount",key=f"bet_amount_{bet}", label_visibility="collapsed")
                    with c8:
                        for bet in st.session_state.user_bets:
                            if (bet.game  == df2.game[counter] and bet.sportsbook == sportsbook and bet.team == df2.away_team[counter]):
                                st.info(f"Payout : {format(payout(st.session_state[f'bet_amount_{bet}'],bet.odds),'.2f')}")
                idx = idx+1
                if(len(game_options) >= idx):
                    with st.container():
                        c1, c2 = st.columns([1,11])
                        with c1:
                            st.write("")
                        with c2:
                            st.caption('---')
        isExpanded = False


    
