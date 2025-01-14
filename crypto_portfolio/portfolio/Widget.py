def Market_State_Widget(num_of_coins: int = 36, height: int = 300):
    html_write = f"""<script src="https://widgets.coingecko.com/coingecko-coin-heatmap-widget.js"></script>
<coingecko-coin-heatmap-widget  height="{height}" locale="en" top="{num_of_coins}"></coingecko-coin-heatmap-widget>
    """
    return html_write


def Scraped():
    html_write = """<div class="sc-1p7xsqe-1 hJhCLj">
                        <div class="treeWrap" id="d3chartw">
                         <div class="heatMapChart" id="d3chart">
                            <svg id="d3svg" width="1338" height="890" paddingTop="10px" class="svg-content-responsive">
                            <gclass="gwrap" stroke-width="1" key="BTC" transform="translate(8,32)">
                            <rect fill="#C5151F" fill-opacity="1" width="737" height="822" stroke="#fff" 
                            class="node level-2">
                            </rect>
                            <rect visibility="visible" width="737" height="822" fill="#fff" fill-opacity="0">
                            </rect>
                            <text fill="#fff" text-anchor="middle" class="shadow" dy="205.5px" y="318.875">
                                <tspan class="symbol" dy="0px" font-size="147.4" x="368.5">BTC</tspan><tspan 
                                class="price" dy="1.4em" font-size="92.125" x="368.5">€38,127.84</tspan><tspan dy="1.4em" 
    font-size="61.416666666666664" x="368.5">▾ 0.67%</tspan><tspan dy="3.2em" font-size="61.416666666666664" 
    x="368.5">Dominance : 41.48%</tspan></text></g><g class="gwrap" stroke-width="1" key="LUNA" transform= 
    "translate(8,854)"><rect fill="#C5151F" fill-opacity="1" width="448" height="36" stroke="#fff" class="node 
    level-2"></rect><rect visibility="visible" width="448" height="36" fill="#fff" fill-opacity="0"></rect><text 
    fill="#fff" text-anchor="middle" class="shadow" dy="9px" y="13.5"><tspan class="symbol" dy="0px" font-size="7.2" 
    x="224">LUNA</tspan><tspan class="price" dy="1.4em" font-size="4.5" x="224">€48.46</tspan><tspan dy="1.4em" 
    font-size="3" x="224">▾ 2.35%</tspan><tspan dy="3.2em" font-size="3" x="224">Dominance : 
    1.12%</tspan></text></g><g class="gwrap" stroke-width="1" key="BCH" transform="translate(456,854)"><rect 
    fill="#16C784" fill-opacity="1" width="129" height="36" stroke="#fff" class="node level-2"></rect><rect 
    visibility="visible" width="129" height="36" fill="#fff" fill-opacity="0"></rect><text fill="#fff" 
    text-anchor="middle" class="shadow" dy="9px" y="13.5"><tspan class="symbol" dy="0px" font-size="7.2" 
    x="64.5">BCH</tspan><tspan class="price" dy="1.4em" font-size="4.5" x="64.5">€296.08</tspan><tspan dy="1.4em" 
    font-size="3" x="64.5">▴ 1.29%</tspan><tspan dy="3.2em" font-size="3" x="64.5">Dominance : 
    0.32%</tspan></text></g><g class="gwrap" stroke-width="1" key="MKR" transform="translate(585,854)"><rect 
    fill="#C5151F" fill-opacity="1" width="44" height="36" stroke="#fff" class="node level-2"></rect><rect 
    visibility="visible" width="44" height="36" fill="#fff" fill-opacity="0"></rect><text fill="#fff" 
    text-anchor="middle" class="shadow" dy="9px" y="13.5"><tspan class="symbol" dy="0px" font-size="7.2" 
    x="22">MKR</tspan><tspan class="price" dy="1.4em" font-size="4.5" x="22">€1,914.24</tspan><tspan dy="1.4em" 
    font-size="3" x="22">▾ 2.04%</tspan><tspan dy="3.2em" font-size="3" x="22">Dominance : 0.11%</tspan></text></g><g 
    class="gwrap" stroke-width="1" key="BSV" transform="translate(629,854)"><rect fill="#C5151F" fill-opacity="1" 
    width="38" height="36" stroke="#fff" class="node level-2"></rect><rect visibility="visible" width="38" 
    height="36" fill="#fff" fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="9px" 
    y="13.5"><tspan class="symbol" dy="0px" font-size="7.2" x="19">BSV</tspan><tspan class="price" dy="1.4em" 
    font-size="4.5" x="19">€87.37</tspan><tspan dy="1.4em" font-size="3" x="19">▾ 0.62%</tspan><tspan dy="3.2em" 
    font-size="3" x="19">Dominance : 0.10%</tspan></text></g><g class="gwrap" stroke-width="1" key="TUSD" 
    transform="translate(667,854)"><rect fill="#C5151F" fill-opacity="1" width="29" height="36" stroke="#fff" 
    class="node level-2"></rect><rect visibility="visible" width="29" height="36" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="9px" y="14.375"><tspan 
    class="symbol" dy="0px" font-size="5.8" x="14.5">TUSD</tspan><tspan class="price" dy="1.4em" font-size="3.625" 
    x="14.5">€0.8754</tspan><tspan dy="1.4em" font-size="2.4166666666666665" x="14.5">▾ 0.02%</tspan><tspan 
    dy="3.2em" font-size="2.4166666666666665" x="14.5">Dominance : 0.07%</tspan></text></g><g class="gwrap" 
    stroke-width="1" key="USDP" transform="translate(696,854)"><rect fill="#C5151F" fill-opacity="1" width="38" 
    height="18" stroke="#fff" class="node level-2"></rect><rect visibility="visible" width="38" height="18" 
    fill="#fff" fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="4.5px" 
    y="6.75"><tspan class="symbol" dy="0px" font-size="3.6" x="19">USDP</tspan><tspan class="price" dy="1.4em" 
    font-size="2.25" x="19">€0.8729</tspan><tspan dy="1.4em" font-size="1.5" x="19">▾ 0.07%</tspan><tspan dy="3.2em" 
    font-size="1.5" x="19">Dominance : 0.05%</tspan></text></g><g class="gwrap" stroke-width="1" key="DCR" 
    transform="translate(696,872)"><rect fill="#C5151F" fill-opacity="1" width="38" height="18" stroke="#fff" 
    class="node level-2"></rect><rect visibility="visible" width="38" height="18" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="4.5px" y="6.75"><tspan 
    class="symbol" dy="0px" font-size="3.6" x="19">DCR</tspan><tspan class="price" dy="1.4em" font-size="2.25" 
    x="19">€57.60</tspan><tspan dy="1.4em" font-size="1.5" x="19">▾ 4.49%</tspan><tspan dy="3.2em" font-size="1.5" 
    x="19">Dominance : 0.05%</tspan></text></g><g class="gwrap" stroke-width="1" key="XNO" transform="translate(734,
    854)"><rect fill="#C5151F" fill-opacity="1" width="11" height="19" stroke="#fff" class="node 
    level-2"></rect><rect visibility="visible" width="11" height="19" fill="#fff" fill-opacity="0"></rect><text 
    fill="#fff" text-anchor="middle" class="shadow" dy="4.75px" y="8.125"><tspan class="symbol" dy="0px" 
    font-size="2.2" x="5.5">XNO</tspan><tspan class="price" dy="1.4em" font-size="1.375" x="5.5">€2.06</tspan><tspan 
    dy="1.4em" font-size="0.9166666666666666" x="5.5">▾ 0.97%</tspan><tspan dy="3.2em" font-size="0.9166666666666666" 
    x="5.5">Dominance : 0.02%</tspan></text></g><g class="gwrap" stroke-width="1" key="RSR" transform="translate(734,
    873)"><rect fill="#C5151F" fill-opacity="1" width="11" height="17" stroke="#fff" class="node 
    level-2"></rect><rect visibility="visible" width="11" height="17" fill="#fff" fill-opacity="0"></rect><text 
    fill="#fff" text-anchor="middle" class="shadow" dy="4.25px" y="7.125"><tspan class="symbol" dy="0px" 
    font-size="2.2" x="5.5">RSR</tspan><tspan class="price" dy="1.4em" font-size="1.375" 
    x="5.5">€0.01764</tspan><tspan dy="1.4em" font-size="0.9166666666666666" x="5.5">▾ 2.18%</tspan><tspan dy="3.2em" 
    font-size="0.9166666666666666" x="5.5">Dominance : 0.01%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="ETH" transform="translate(753,32)"><rect fill="#16C784" fill-opacity="1" width="577" height="470" 
    stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="577" height="470" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="117.5px" y="176.25"><tspan 
    class="symbol" dy="0px" font-size="94" x="288.5">ETH</tspan><tspan class="price" dy="1.4em" font-size="58.75" 
    x="288.5">€2,740.33</tspan><tspan dy="1.4em" font-size="39.166666666666664" x="288.5">▴ 0.65%</tspan><tspan 
    dy="3.2em" font-size="39.166666666666664" x="288.5">Dominance : 18.78%</tspan></text></g><g class="gwrap" 
    stroke-width="1" key="BNB" transform="translate(753,502)"><rect fill="#C5151F" fill-opacity="1" width="240" 
    height="208" stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="240" height="208" 
    fill="#fff" fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="52px" y="78"><tspan 
    class="symbol" dy="0px" font-size="41.6" x="120">BNB</tspan><tspan class="price" dy="1.4em" font-size="26" 
    x="120">€364.76</tspan><tspan dy="1.4em" font-size="17.333333333333332" x="120">▾ 2.07%</tspan><tspan dy="3.2em" 
    font-size="17.333333333333332" x="120">Dominance : 3.46%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="ADA" transform="translate(993,502)"><rect fill="#C5151F" fill-opacity="1" width="214" height="135" 
    stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="214" height="135" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="33.75px" y="50.625"><tspan 
    class="symbol" dy="0px" font-size="27" x="107">ADA</tspan><tspan class="price" dy="1.4em" font-size="16.875" 
    x="107">€1.04</tspan><tspan dy="1.4em" font-size="11.25" x="107">▾ 0.39%</tspan><tspan dy="3.2em" 
    font-size="11.25" x="107">Dominance : 2.00%</tspan></text></g><g class="gwrap" stroke-width="1" key="AVAX" 
    transform="translate(993,637)"><rect fill="#C5151F" fill-opacity="1" width="214" height="73" stroke="#fff" 
    class="node level-2"></rect><rect visibility="hidden" width="214" height="73" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="18.25px" y="27.375"><tspan 
    class="symbol" dy="0px" font-size="14.6" x="107">AVAX</tspan><tspan class="price" dy="1.4em" font-size="9.125" 
    x="107">€77.69</tspan><tspan dy="1.4em" font-size="6.083333333333333" x="107">▾ 1.99%</tspan><tspan dy="3.2em" 
    font-size="6.083333333333333" x="107">Dominance : 1.09%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="LINK" transform="translate(1207,502)"><rect fill="#C5151F" fill-opacity="1" width="69" height="90" 
    stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="69" height="90" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="22.5px" y="36.375"><tspan 
    class="symbol" dy="0px" font-size="13.8" x="34.5">LINK</tspan><tspan class="price" dy="1.4em" font-size="8.625" 
    x="34.5">€15.90</tspan><tspan dy="1.4em" font-size="5.75" x="34.5">▾ 0.31%</tspan><tspan dy="3.2em" 
    font-size="5.75" x="34.5">Dominance : 0.43%</tspan></text></g><g class="gwrap" stroke-width="1" key="ALGO" 
    transform="translate(1276,502)"><rect fill="#16C784" fill-opacity="1" width="54" height="90" stroke="#fff" 
    class="node level-2"></rect><rect visibility="hidden" width="54" height="90" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="22.5px" y="38.25"><tspan 
    class="symbol" dy="0px" font-size="10.8" x="27">ALGO</tspan><tspan class="price" dy="1.4em" font-size="6.75" 
    x="27">€0.8948</tspan><tspan dy="1.4em" font-size="4.5" x="27">▴ 0.23%</tspan><tspan dy="3.2em" font-size="4.5" 
    x="27">Dominance : 0.34%</tspan></text></g><g class="gwrap" stroke-width="1" key="XLM" transform="translate(1207,
    592)"><rect fill="#C5151F" fill-opacity="1" width="71" height="60" stroke="#fff" class="node 
    level-2"></rect><rect visibility="hidden" width="71" height="60" fill="#fff" fill-opacity="0"></rect><text 
    fill="#fff" text-anchor="middle" class="shadow" dy="15px" y="22.5"><tspan class="symbol" dy="0px" font-size="12" 
    x="35.5">XLM</tspan><tspan class="price" dy="1.4em" font-size="7.5" x="35.5">€0.2078</tspan><tspan dy="1.4em" 
    font-size="5" x="35.5">▾ 0.58%</tspan><tspan dy="3.2em" font-size="5" x="35.5">Dominance : 
    0.30%</tspan></text></g><g class="gwrap" stroke-width="1" key="FTM" transform="translate(1207,652)"><rect 
    fill="#C5151F" fill-opacity="1" width="71" height="58" stroke="#fff" class="node level-2"></rect><rect 
    visibility="hidden" width="71" height="58" fill="#fff" fill-opacity="0"></rect><text fill="#fff" 
    text-anchor="middle" class="shadow" dy="14.5px" y="21.75"><tspan class="symbol" dy="0px" font-size="11.6" 
    x="35.5">FTM</tspan><tspan class="price" dy="1.4em" font-size="7.25" x="35.5">€1.94</tspan><tspan dy="1.4em" 
    font-size="4.833333333333333" x="35.5">▾ 1.97%</tspan><tspan dy="3.2em" font-size="4.833333333333333" 
    x="35.5">Dominance : 0.28%</tspan></text></g><g class="gwrap" stroke-width="1" key="ETC" transform="translate(
    1278,592)"><rect fill="#16C784" fill-opacity="1" width="52" height="61" stroke="#fff" class="node 
    level-2"></rect><rect visibility="hidden" width="52" height="61" fill="#fff" fill-opacity="0"></rect><text 
    fill="#fff" text-anchor="middle" class="shadow" dy="15.25px" y="24"><tspan class="symbol" dy="0px" 
    font-size="10.4" x="26">ETC</tspan><tspan class="price" dy="1.4em" font-size="6.5" x="26">€29.43</tspan><tspan 
    dy="1.4em" font-size="4.333333333333333" x="26">▴ 7.19%</tspan><tspan dy="3.2em" font-size="4.333333333333333" 
    x="26">Dominance : 0.22%</tspan></text></g><g class="gwrap" stroke-width="1" key="VET" transform="translate(1278,
    653)"><rect fill="#C5151F" fill-opacity="1" width="52" height="57" stroke="#fff" class="node 
    level-2"></rect><rect visibility="hidden" width="52" height="57" fill="#fff" fill-opacity="0"></rect><text 
    fill="#fff" text-anchor="middle" class="shadow" dy="14.25px" y="22"><tspan class="symbol" dy="0px" 
    font-size="10.4" x="26">VET</tspan><tspan class="price" dy="1.4em" font-size="6.5" x="26">€0.05616</tspan><tspan 
    dy="1.4em" font-size="4.333333333333333" x="26">▾ 1.02%</tspan><tspan dy="3.2em" font-size="4.333333333333333" 
    x="26">Dominance : 0.21%</tspan></text></g><g class="gwrap" stroke-width="1" key="DOGE" transform="translate(753,
    742)"><rect fill="#C5151F" fill-opacity="1" width="155" height="81" stroke="#fff" class="node 
    level-2"></rect><rect visibility="visible" width="155" height="81" fill="#fff" fill-opacity="0"></rect><text 
    fill="#fff" text-anchor="middle" class="shadow" dy="20.25px" y="30.375"><tspan class="symbol" dy="0px" 
    font-size="16.2" x="77.5">DOGE</tspan><tspan class="price" dy="1.4em" font-size="10.125" 
    x="77.5">€0.1373</tspan><tspan dy="1.4em" font-size="6.75" x="77.5">▾ 1.42%</tspan><tspan dy="3.2em" 
    font-size="6.75" x="77.5">Dominance : 1.05%</tspan></text></g><g class="gwrap" stroke-width="1" key="SHIB" 
    transform="translate(753,823)"><rect fill="#C5151F" fill-opacity="1" width="155" height="67" stroke="#fff" 
    class="node level-2"></rect><rect visibility="visible" width="155" height="67" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="16.75px" y="25.125"><tspan 
    class="symbol" dy="0px" font-size="13.4" x="77.5">SHIB</tspan><tspan class="price" dy="1.4em" font-size="8.375" 
    x="77.5">€0.00002747</tspan><tspan dy="1.4em" font-size="5.583333333333333" x="77.5">▾ 5.1%</tspan><tspan 
    dy="3.2em" font-size="5.583333333333333" x="77.5">Dominance : 0.87%</tspan></text></g><g class="gwrap" 
    stroke-width="1" key="ELON" transform="translate(908,742)"><rect fill="#C5151F" fill-opacity="1" width="4" 
    height="97" stroke="#fff" class="node level-2"></rect><rect visibility="visible" width="4" height="97" 
    fill="#fff" fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="24.25px" 
    y="48"><tspan class="symbol" dy="0px" font-size="0.8" x="2">ELON</tspan><tspan class="price" dy="1.4em" 
    font-size="0.5" x="2">€0.0000009534</tspan><tspan dy="1.4em" font-size="0.3333333333333333" x="2">▾ 
    0.9%</tspan><tspan dy="3.2em" font-size="0.3333333333333333" x="2">Dominance : 0.03%</tspan></text></g><g 
    class="gwrap" stroke-width="1" key="SAMO" transform="translate(908,839)"><rect fill="#C5151F" fill-opacity="1" 
    width="4" height="14" stroke="#fff" class="node level-2"></rect><rect visibility="visible" width="4" height="14" 
    fill="#fff" fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="3.5px" 
    y="6.5"><tspan class="symbol" dy="0px" font-size="0.8" x="2">SAMO</tspan><tspan class="price" dy="1.4em" 
    font-size="0.5" x="2">€0.02352</tspan><tspan dy="1.4em" font-size="0.3333333333333333" x="2">▾ 
    2.04%</tspan><tspan dy="3.2em" font-size="0.3333333333333333" x="2">Dominance : 0%</tspan></text></g><g 
    class="gwrap" stroke-width="1" key="MONA" transform="translate(908,853)"><rect fill="#16C784" fill-opacity="1" 
    width="4" height="12" stroke="#fff" class="node level-2"></rect><rect visibility="visible" width="4" height="12" 
    fill="#fff" fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="3px" y="5.5"><tspan 
    class="symbol" dy="0px" font-size="0.8" x="2">MONA</tspan><tspan class="price" dy="1.4em" font-size="0.5" 
    x="2">€0.9828</tspan><tspan dy="1.4em" font-size="0.3333333333333333" x="2">▴ 0.17%</tspan><tspan dy="3.2em" 
    font-size="0.3333333333333333" x="2">Dominance : 0%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="HOGE" transform="translate(908,865)"><rect fill="#A4111A" fill-opacity="1" width="4" height="8" 
    stroke="#fff" class="node level-2"></rect><rect visibility="visible" width="4" height="8" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="2px" y="3.5"><tspan 
    class="symbol" dy="0px" font-size="0.8" x="2">HOGE</tspan><tspan class="price" dy="1.4em" font-size="0.5" 
    x="2">€0.0001069</tspan><tspan dy="1.4em" font-size="0.3333333333333333" x="2">▾ 8.12%</tspan><tspan dy="3.2em" 
    font-size="0.3333333333333333" x="2">Dominance : 0%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="ERC20" transform="translate(908,873)"><rect fill="#16C784" fill-opacity="1" width="4" height="6" 
    stroke="#fff" class="node level-2"></rect><rect visibility="visible" width="4" height="6" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="1.5px" y="2.5"><tspan 
    class="symbol" dy="0px" font-size="0.8" x="2">ERC20</tspan><tspan class="price" dy="1.4em" font-size="0.5" 
    x="2">€0.03051</tspan><tspan dy="1.4em" font-size="0.3333333333333333" x="2">▴ 2.41%</tspan><tspan dy="3.2em" 
    font-size="0.3333333333333333" x="2">Dominance : 0%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="DOBO" transform="translate(908,879)"><rect fill="#C5151F" fill-opacity="1" width="4" height="5" 
    stroke="#fff" class="node level-2"></rect><rect visibility="visible" width="4" height="5" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="1.25px" y="2"><tspan 
    class="symbol" dy="0px" font-size="0.8" x="2">DOBO</tspan><tspan class="price" dy="1.4em" font-size="0.5" 
    x="2">€0.00000004626</tspan><tspan dy="1.4em" font-size="0.3333333333333333" x="2">▾ 2.4%</tspan><tspan 
    dy="3.2em" font-size="0.3333333333333333" x="2">Dominance : 0%</tspan></text></g><g class="gwrap" 
    stroke-width="1" key="BAN" transform="translate(908,884)"><rect fill="#16C784" fill-opacity="1" width="2" 
    height="6" stroke="#fff" class="node level-2"></rect><rect visibility="visible" width="2" height="6" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="1.5px" y="2.75"><tspan 
    class="symbol" dy="0px" font-size="0.4" x="1">BAN</tspan><tspan class="price" dy="1.4em" font-size="0.25" 
    x="1">€0.01214</tspan><tspan dy="1.4em" font-size="0.16666666666666666" x="1">▴ 0.11%</tspan><tspan dy="3.2em" 
    font-size="0.16666666666666666" x="1">Dominance : 0%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="DOGEDASH" transform="translate(910,884)"><rect fill="#16C784" fill-opacity="1" width="2" height="6" 
    stroke="#fff" class="node level-2"></rect><rect visibility="visible" width="2" height="6" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="1.5px" y="2.75"><tspan 
    class="symbol" dy="0px" font-size="0.4" x="1">DOGEDASH</tspan><tspan class="price" dy="1.4em" font-size="0.25" 
    x="1">€0.000269</tspan><tspan dy="1.4em" font-size="0.16666666666666666" x="1">▴ 1.75%</tspan><tspan dy="3.2em" 
    font-size="0.16666666666666666" x="1">Dominance : 0%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="WBTC" transform="translate(920,742)"><rect fill="#C5151F" fill-opacity="1" width="88" height="79" 
    stroke="#fff" class="node level-2"></rect><rect visibility="visible" width="88" height="79" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="19.75px" y="29.625"><tspan 
    class="symbol" dy="0px" font-size="15.8" x="44">WBTC</tspan><tspan class="price" dy="1.4em" font-size="9.875" 
    x="44">€38,182.71</tspan><tspan dy="1.4em" font-size="6.583333333333333" x="44">▾ 0.6%</tspan><tspan dy="3.2em" 
    font-size="6.583333333333333" x="44">Dominance : 0.57%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="DAI" transform="translate(920,821)"><rect fill="#C5151F" fill-opacity="1" width="88" height="69" 
    stroke="#fff" class="node level-2"></rect><rect visibility="visible" width="88" height="69" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="17.25px" y="25.875"><tspan 
    class="symbol" dy="0px" font-size="13.8" x="44">DAI</tspan><tspan class="price" dy="1.4em" font-size="8.625" 
    x="44">€0.8755</tspan><tspan dy="1.4em" font-size="5.75" x="44">▾ 0.02%</tspan><tspan dy="3.2em" font-size="5.75" 
    x="44">Dominance : 0.51%</tspan></text></g><g class="gwrap" stroke-width="1" key="UNI" transform="translate(1008,
    742)"><rect fill="#16C784" fill-opacity="1" width="67" height="70" stroke="#fff" class="node 
    level-2"></rect><rect visibility="visible" width="67" height="70" fill="#fff" fill-opacity="0"></rect><text 
    fill="#fff" text-anchor="middle" class="shadow" dy="17.5px" y="26.625"><tspan class="symbol" dy="0px" 
    font-size="13.4" x="33.5">UNI</tspan><tspan class="price" dy="1.4em" font-size="8.375" 
    x="33.5">€10.80</tspan><tspan dy="1.4em" font-size="5.583333333333333" x="33.5">▴ 2.29%</tspan><tspan dy="3.2em" 
    font-size="5.583333333333333" x="33.5">Dominance : 0.39%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="XTZ" transform="translate(1008,812)"><rect fill="#119563" fill-opacity="1" width="41" height="58" 
    stroke="#fff" class="node level-2"></rect><rect visibility="visible" width="41" height="58" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="14.5px" y="23.875"><tspan 
    class="symbol" dy="0px" font-size="8.2" x="20.5">XTZ</tspan><tspan class="price" dy="1.4em" font-size="5.125" 
    x="20.5">€3.99</tspan><tspan dy="1.4em" font-size="3.4166666666666665" x="20.5">▴ 11.43%</tspan><tspan dy="3.2em" 
    font-size="3.4166666666666665" x="20.5">Dominance : 0.20%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="AAVE" transform="translate(1049,812)"><rect fill="#16C784" fill-opacity="1" width="26" height="58" 
    stroke="#fff" class="node level-2"></rect><rect visibility="visible" width="26" height="58" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="14.5px" y="25.75"><tspan 
    class="symbol" dy="0px" font-size="5.2" x="13">AAVE</tspan><tspan class="price" dy="1.4em" font-size="3.25" 
    x="13">€160.65</tspan><tspan dy="1.4em" font-size="2.1666666666666665" x="13">▴ 1.18%</tspan><tspan dy="3.2em" 
    font-size="2.1666666666666665" x="13">Dominance : 0.12%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="GRT" transform="translate(1008,870)"><rect fill="#C5151F" fill-opacity="1" width="67" height="20" 
    stroke="#fff" class="node level-2"></rect><rect visibility="visible" width="67" height="20" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="5px" y="7.5"><tspan 
    class="symbol" dy="0px" font-size="4" x="33.5">GRT</tspan><tspan class="price" dy="1.4em" font-size="2.5" 
    x="33.5">€0.4111</tspan><tspan dy="1.4em" font-size="1.6666666666666667" x="33.5">▾ 0.4%</tspan><tspan dy="3.2em" 
    font-size="1.6666666666666667" x="33.5">Dominance : 0.11%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="CRO" transform="translate(1083,742)"><rect fill="#C5151F" fill-opacity="1" width="96" height="65" 
    stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="96" height="65" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="16.25px" y="24.375"><tspan 
    class="symbol" dy="0px" font-size="13" x="48">CRO</tspan><tspan class="price" dy="1.4em" font-size="8.125" 
    x="48">€0.4306</tspan><tspan dy="1.4em" font-size="5.416666666666667" x="48">▾ 2.79%</tspan><tspan dy="3.2em" 
    font-size="5.416666666666667" x="48">Dominance : 0.62%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="LEO" transform="translate(1179,742)"><rect fill="#0E7C53" fill-opacity="1" width="55" height="65" 
    stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="55" height="65" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="16.25px" y="25.625"><tspan 
    class="symbol" dy="0px" font-size="11" x="27.5">LEO</tspan><tspan class="price" dy="1.4em" font-size="6.875" 
    x="27.5">€6.50</tspan><tspan dy="1.4em" font-size="4.583333333333333" x="27.5">▴ 51.84%</tspan><tspan dy="3.2em" 
    font-size="4.583333333333333" x="27.5">Dominance : 0.36%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="FTT" transform="translate(1234,742)"><rect fill="#C5151F" fill-opacity="1" width="49" height="65" 
    stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="49" height="65" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="16.25px" y="26.375"><tspan 
    class="symbol" dy="0px" font-size="9.8" x="24.5">FTT</tspan><tspan class="price" dy="1.4em" font-size="6.125" 
    x="24.5">€40.48</tspan><tspan dy="1.4em" font-size="4.083333333333333" x="24.5">▾ 0.72%</tspan><tspan dy="3.2em" 
    font-size="4.083333333333333" x="24.5">Dominance : 0.32%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="KCS" transform="translate(1283,742)"><rect fill="#16C784" fill-opacity="1" width="24" height="34" 
    stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="24" height="34" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="8.5px" y="14"><tspan 
    class="symbol" dy="0px" font-size="4.8" x="12">KCS</tspan><tspan class="price" dy="1.4em" font-size="3" 
    x="12">€18.04</tspan><tspan dy="1.4em" font-size="2" x="12">▴ 0.41%</tspan><tspan dy="3.2em" font-size="2" 
    x="12">Dominance : 0.08%</tspan></text></g><g class="gwrap" stroke-width="1" key="HT" transform="translate(1307,
    742)"><rect fill="#16C784" fill-opacity="1" width="23" height="34" stroke="#fff" class="node 
    level-2"></rect><rect visibility="hidden" width="23" height="34" fill="#fff" fill-opacity="0"></rect><text 
    fill="#fff" text-anchor="middle" class="shadow" dy="8.5px" y="14.125"><tspan class="symbol" dy="0px" 
    font-size="4.6" x="11.5">HT</tspan><tspan class="price" dy="1.4em" font-size="2.875" x="11.5">€8.76</tspan><tspan 
    dy="1.4em" font-size="1.9166666666666667" x="11.5">▴ 0.11%</tspan><tspan dy="3.2em" 
    font-size="1.9166666666666667" x="11.5">Dominance : 0.08%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="OKB" transform="translate(1283,776)"><rect fill="#16C784" fill-opacity="1" width="33" height="21" 
    stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="33" height="21" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="5.25px" y="7.875"><tspan 
    class="symbol" dy="0px" font-size="4.2" x="16.5">OKB</tspan><tspan class="price" dy="1.4em" font-size="2.625" 
    x="16.5">€20.17</tspan><tspan dy="1.4em" font-size="1.75" x="16.5">▴ 2.56%</tspan><tspan dy="3.2em" 
    font-size="1.75" x="16.5">Dominance : 0.07%</tspan></text></g><g class="gwrap" stroke-width="1" key="WOO" 
    transform="translate(1283,797)"><rect fill="#C5151F" fill-opacity="1" width="33" height="10" stroke="#fff" 
    class="node level-2"></rect><rect visibility="hidden" width="33" height="10" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="2.5px" y="3.75"><tspan 
    class="symbol" dy="0px" font-size="2" x="16.5">WOO</tspan><tspan class="price" dy="1.4em" font-size="1.25" 
    x="16.5">€0.6346</tspan><tspan dy="1.4em" font-size="0.8333333333333334" x="16.5">▾ 4.37%</tspan><tspan 
    dy="3.2em" font-size="0.8333333333333334" x="16.5">Dominance : 0.03%</tspan></text></g><g class="gwrap" 
    stroke-width="1" key="GT" transform="translate(1316,776)"><rect fill="#C5151F" fill-opacity="1" width="14" 
    height="20" stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="14" height="20" 
    fill="#fff" fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="5px" 
    y="8.25"><tspan class="symbol" dy="0px" font-size="2.8" x="7">GT</tspan><tspan class="price" dy="1.4em" 
    font-size="1.75" x="7">€5.98</tspan><tspan dy="1.4em" font-size="1.1666666666666667" x="7">▾ 4.09%</tspan><tspan 
    dy="3.2em" font-size="1.1666666666666667" x="7">Dominance : 0.03%</tspan></text></g><g class="gwrap" 
    stroke-width="1" key="WRX" transform="translate(1316,796)"><rect fill="#16C784" fill-opacity="1" width="14" 
    height="11" stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="14" height="11" 
    fill="#fff" fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="2.75px" 
    y="4.125"><tspan class="symbol" dy="0px" font-size="2.2" x="7">WRX</tspan><tspan class="price" dy="1.4em" 
    font-size="1.375" x="7">€0.8521</tspan><tspan dy="1.4em" font-size="0.9166666666666666" x="7">▴ 
    0.48%</tspan><tspan dy="3.2em" font-size="0.9166666666666666" x="7">Dominance : 0.02%</tspan></text></g><g 
    class="gwrap" stroke-width="1" key="MANA" transform="translate(1083,839)"><rect fill="#16C784" fill-opacity="1" 
    width="55" height="51" stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="55" height="51" 
    fill="#fff" fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="12.75px" 
    y="19.125"><tspan class="symbol" dy="0px" font-size="10.2" x="27.5">MANA</tspan><tspan class="price" dy="1.4em" 
    font-size="6.375" x="27.5">€2.93</tspan><tspan dy="1.4em" font-size="4.25" x="27.5">▴ 5.71%</tspan><tspan 
    dy="3.2em" font-size="4.25" x="27.5">Dominance : 0.31%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="SAND" transform="translate(1138,839)"><rect fill="#16C784" fill-opacity="1" width="43" height="51" 
    stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="43" height="51" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="12.75px" y="20.125"><tspan 
    class="symbol" dy="0px" font-size="8.6" x="21.5">SAND</tspan><tspan class="price" dy="1.4em" font-size="5.375" 
    x="21.5">€4.05</tspan><tspan dy="1.4em" font-size="3.5833333333333335" x="21.5">▴ 4.11%</tspan><tspan dy="3.2em" 
    font-size="3.5833333333333335" x="21.5">Dominance : 0.24%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="AXS" transform="translate(1181,839)"><rect fill="#16C784" fill-opacity="1" width="66" height="28" 
    stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="66" height="28" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="7px" y="10.5"><tspan 
    class="symbol" dy="0px" font-size="5.6" x="33">AXS</tspan><tspan class="price" dy="1.4em" font-size="3.5" 
    x="33">€57.18</tspan><tspan dy="1.4em" font-size="2.3333333333333335" x="33">▴ 1.76%</tspan><tspan dy="3.2em" 
    font-size="2.3333333333333335" x="33">Dominance : 0.20%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="THETA" transform="translate(1181,867)"><rect fill="#16C784" fill-opacity="1" width="66" height="23" 
    stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="66" height="23" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="5.75px" y="8.625"><tspan 
    class="symbol" dy="0px" font-size="4.6" x="33">THETA</tspan><tspan class="price" dy="1.4em" font-size="2.875" 
    x="33">€2.94</tspan><tspan dy="1.4em" font-size="1.9166666666666667" x="33">▴ 0.86%</tspan><tspan dy="3.2em" 
    font-size="1.9166666666666667" x="33">Dominance : 0.17%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="GALA" transform="translate(1247,839)"><rect fill="#16C784" fill-opacity="1" width="43" height="27" 
    stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="43" height="27" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="6.75px" y="10.125"><tspan 
    class="symbol" dy="0px" font-size="5.4" x="21.5">GALA</tspan><tspan class="price" dy="1.4em" font-size="3.375" 
    x="21.5">€0.3156</tspan><tspan dy="1.4em" font-size="2.25" x="21.5">▴ 6.08%</tspan><tspan dy="3.2em" 
    font-size="2.25" x="21.5">Dominance : 0.13%</tspan></text></g><g class="gwrap" stroke-width="1" key="FLOW" 
    transform="translate(1247,866)"><rect fill="#16C784" fill-opacity="1" width="43" height="24" stroke="#fff" 
    class="node level-2"></rect><rect visibility="hidden" width="43" height="24" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="6px" y="9"><tspan 
    class="symbol" dy="0px" font-size="4.8" x="21.5">FLOW</tspan><tspan class="price" dy="1.4em" font-size="3" 
    x="21.5">€6.34</tspan><tspan dy="1.4em" font-size="2" x="21.5">▴ 0.31%</tspan><tspan dy="3.2em" font-size="2" 
    x="21.5">Dominance : 0.12%</tspan></text></g><g class="gwrap" stroke-width="1" key="ENJ" transform="translate(
    1290,839)"><rect fill="#16C784" fill-opacity="1" width="23" height="36" stroke="#fff" class="node 
    level-2"></rect><rect visibility="hidden" width="23" height="36" fill="#fff" fill-opacity="0"></rect><text 
    fill="#fff" text-anchor="middle" class="shadow" dy="9px" y="15.125"><tspan class="symbol" dy="0px" 
    font-size="4.6" x="11.5">ENJ</tspan><tspan class="price" dy="1.4em" font-size="2.875" 
    x="11.5">€1.81</tspan><tspan dy="1.4em" font-size="1.9166666666666667" x="11.5">▴ 3.72%</tspan><tspan dy="3.2em" 
    font-size="1.9166666666666667" x="11.5">Dominance : 0.09%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="CHZ" transform="translate(1313,839)"><rect fill="#16C784" fill-opacity="1" width="17" height="36" 
    stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="17" height="36" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="9px" y="15.875"><tspan 
    class="symbol" dy="0px" font-size="3.4" x="8.5">CHZ</tspan><tspan class="price" dy="1.4em" font-size="2.125" 
    x="8.5">€0.1949</tspan><tspan dy="1.4em" font-size="1.4166666666666667" x="8.5">▴ 0.35%</tspan><tspan dy="3.2em" 
    font-size="1.4166666666666667" x="8.5">Dominance : 0.07%</tspan></text></g><g class="gwrap" stroke-width="1" 
    key="ROSE" transform="translate(1290,875)"><rect fill="#16C784" fill-opacity="1" width="40" height="15" 
    stroke="#fff" class="node level-2"></rect><rect visibility="hidden" width="40" height="15" fill="#fff" 
    fill-opacity="0"></rect><text fill="#fff" text-anchor="middle" class="shadow" dy="3.75px" y="5.625"><tspan 
    class="symbol" dy="0px" font-size="3" x="20">ROSE</tspan><tspan class="price" dy="1.4em" font-size="1.875" 
    x="20">€0.3277</tspan><tspan dy="1.4em" font-size="1.25" x="20">▴ 1.94%</tspan><tspan dy="3.2em" font-size="1.25" 
    x="20">Dominance : 0.07%</tspan></text></g><g x="4" y="0" dx="753" dy="890"><text x="9" y="21" font-size="14px" 
    font-weight="600" fill="#333">Store Of Value</text></g><g x="749" y="0" dx="2083" dy="710"><text x="754" y="21" 
    font-size="14px" font-weight="600" fill="#333">Smart Contracts</text></g><g x="749" y="710" dx="1665" 
    dy="1600"><text x="754" y="731" font-size="14px" font-weight="600" fill="#333">Memes</text></g><g x="916" y="710" 
    dx="1995" dy="1600"><text x="921" y="731" font-size="14px" font-weight="600" fill="#333">DeFi</text></g><g 
    x="1079" y="710" dx="2413" dy="1517"><text x="1084" y="731" font-size="14px" font-weight="600" 
    fill="#333">Centralized Exchange</text></g><g x="1079" y="807" dx="2413" dy="1697"><text x="1084" y="828" 
    font-size="14px" font-weight="600" fill="#333">NFTs</text></g></svg></div><div id="chartToolTip" class="tooltip 
    chartToolTip" style="opacity: 0; left: 829px; top: 666px;"><ul class="tooltipBody"> <li 
    style="background-image:url(https://s2.coinmarketcap.com/static/img/coins/64x64/1839.png)"><span 
    class="black">bnb</span><span class="gray">BNB</span></li> <li><span class="gray">Price:</span><span 
    class="black">€364.76</span><span class="red">▾2.07%</span></li> <li><span class="gray">Market  Cap:</span><span 
    class="black">€60,228,010,224.15</span></li> <li><span class="gray">Volume(24h):</span><span class="black">€1,
    812,703,884.27</span></li> </ul></div></div></div> """
    return html_write
