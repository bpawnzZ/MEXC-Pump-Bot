import ccxt
import datetime as dt
from datetime import datetime
import time
from termcolor import colored
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",  # Removed [INFO] prefix
    handlers=[
        logging.FileHandler("pump_bot.log"),
        logging.StreamHandler()
    ]
)

# MEXC API credentials
api_key = os.getenv("API_KEY")
api_secret = os.getenv("API_SECRET")

# Initialize MEXC exchange
mexc = ccxt.mexc({
    'apiKey': api_key,
    'secret': api_secret,
    'enableRateLimit': True,
})

# Configuration
show_only_pair = "USDT"  # Select nothing for all, only selected currency will be shown
show_limit = 1           # Minimum top query limit
min_perc = 0.05          # Minimum percentage change

price_changes = []
price_groups = {}

class PriceChange:
    def __init__(self, symbol, prev_price, price, total_trades, open, volume, isPrinted, event_time, prev_volume):
        self.symbol = symbol
        self.prev_price = prev_price
        self.price = price
        self.total_trades = total_trades
        self.open = open
        self.volume = volume
        self.isPrinted = isPrinted
        self.event_time = event_time
        self.prev_volume = prev_volume

    @property
    def volume_change(self):
        return self.volume - self.prev_volume

    @property
    def volume_change_perc(self):
        if self.prev_volume == 0:
            return 0
        return self.volume_change / self.prev_volume * 100

    @property
    def price_change(self):
        return self.price - self.prev_price

    @property
    def price_change_perc(self):
        if self.prev_price == 0 or self.price == 0:
            return 0
        return self.price_change / self.prev_price * 100

class PriceGroup:
    def __init__(self, symbol, tick_count, total_price_change, relative_price_change, total_volume_change, last_price, last_event_time, open, volume, isPrinted):
        self.symbol = symbol
        self.tick_count = tick_count
        self.total_price_change = total_price_change
        self.relative_price_change = relative_price_change
        self.total_volume_change = total_volume_change
        self.last_price = last_price
        self.last_event_time = last_event_time
        self.open = open
        self.volume = volume
        self.isPrinted = isPrinted

    def to_string(self, isColored):
        self.isPrinted = True
        retval = "Symbol:{}\t Time:{}\t Ticks:{}\t RPCh:{}\t TPCh:{}\t VCh:{}\t LP:{}\t LV:{}\t".format(
            self.symbol,
            self.last_event_time,
            self.tick_count,
            "{0:2.2f}".format(self.relative_price_change),
            "{0:2.2f}".format(self.total_price_change),
            "{0:2.2f}".format(self.total_volume_change),
            self.last_price,
            self.volume
        )
        if not isColored:
            return retval
        else:
            return colored(retval, self.console_color)

    @property
    def console_color(self):
        if self.relative_price_change < 0:
            return 'red'
        else:
            return 'green'

def process_tickers(tickers):
    for symbol, ticker in tickers.items():
        if not show_only_pair in symbol:
            continue

        # Check if required fields are not None
        if ticker.get('last') is None or ticker.get('open') is None or ticker.get('baseVolume') is None:
            continue  # Silently skip invalid data

        price = float(ticker['last'])
        total_trades = ticker['info'].get('count', 0)
        open = float(ticker['open'])
        volume = float(ticker['baseVolume'])
        event_time = datetime.fromtimestamp(ticker['timestamp'] / 1000)

        if len(price_changes) > 0:
            price_change = next((item for item in price_changes if item.symbol == symbol), None)
            if price_change:
                price_change.event_time = event_time
                price_change.prev_price = price_change.price
                price_change.prev_volume = price_change.volume
                price_change.price = price
                price_change.total_trades = total_trades
                price_change.open = open
                price_change.volume = volume
                price_change.isPrinted = False
            else:
                price_changes.append(PriceChange(symbol, price, price, total_trades, open, volume, False, event_time, volume))
        else:
            price_changes.append(PriceChange(symbol, price, price, total_trades, open, volume, False, event_time, volume))

    price_changes.sort(key=lambda x: x.price_change_perc, reverse=True)

    for price_change in price_changes:
        if (not price_change.isPrinted
            and abs(price_change.price_change_perc) > min_perc
            and price_change.volume_change_perc > min_perc):
            price_change.isPrinted = True
            if not price_change.symbol in price_groups:
                price_groups[price_change.symbol] = PriceGroup(price_change.symbol, 1, abs(price_change.price_change_perc), price_change.price_change_perc, price_change.volume_change_perc, price_change.price, price_change.event_time, price_change.open, price_change.volume, False)
            else:
                price_groups[price_change.symbol].tick_count += 1
                price_groups[price_change.symbol].last_event_time = price_change.event_time
                price_groups[price_change.symbol].volume = price_change.volume
                price_groups[price_change.symbol].last_price = price_change.price
                price_groups[price_change.symbol].isPrinted = False
                price_groups[price_change.symbol].total_price_change += abs(price_change.price_change_perc)
                price_groups[price_change.symbol].relative_price_change += price_change.price_change_perc
                price_groups[price_change.symbol].total_volume_change += price_change.volume_change_perc

    if len(price_groups) > 0:
        anyPrinted = False
        sorted_price_group = sorted(price_groups, key=lambda k: price_groups[k].tick_count, reverse=True)
        for s in range(show_limit):
            if s < len(sorted_price_group):
                max_price_group = price_groups[sorted_price_group[s]]
                if not max_price_group.isPrinted:
                    logging.info(colored("Top Ticks", attrs=["bold"]))  # Make header bold
                    logging.info(max_price_group.to_string(True))
                    anyPrinted = True

        sorted_price_group = sorted(price_groups, key=lambda k: price_groups[k].total_price_change, reverse=True)
        for s in range(show_limit):
            if s < len(sorted_price_group):
                max_price_group = price_groups[sorted_price_group[s]]
                if not max_price_group.isPrinted:
                    logging.info(colored("Top Total Price Change", attrs=["bold"]))  # Make header bold
                    logging.info(max_price_group.to_string(True))
                    anyPrinted = True

        sorted_price_group = sorted(price_groups, key=lambda k: abs(price_groups[k].relative_price_change), reverse=True)
        for s in range(show_limit):
            if s < len(sorted_price_group):
                max_price_group = price_groups[sorted_price_group[s]]
                if not max_price_group.isPrinted:
                    logging.info(colored("Top Relative Price Change", attrs=["bold"]))  # Make header bold
                    logging.info(max_price_group.to_string(True))
                    anyPrinted = True

        sorted_price_group = sorted(price_groups, key=lambda k: price_groups[k].total_volume_change, reverse=True)
        for s in range(show_limit):
            if s < len(sorted_price_group):
                max_price_group = price_groups[sorted_price_group[s]]
                if not max_price_group.isPrinted:
                    logging.info(colored("Top Total Volume Change", attrs=["bold"]))  # Make header bold
                    logging.info(max_price_group.to_string(True))
                    anyPrinted = True

        if anyPrinted:
            logging.info("")

def main():
    while True:
        try:
            tickers = mexc.fetch_tickers()
            process_tickers(tickers)
        except Exception as e:
            logging.error(f"Error fetching ticker data: {e}")
        time.sleep(10)  # Fetch data every 10 seconds

if __name__ == "__main__":
    main()
