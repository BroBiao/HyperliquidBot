#from hyperliquid.info import Info
from hyperliquid.utils import constants
#from hyperliquid.exchange import Exchange
import utils


address, info, exchange = utils.setup(base_url=constants.TESTNET_API_URL, skip_ws=True)

# 查账户
user_state = info.spot_user_state(address)
#print(user_state)

# 查成交
user_fills = info.user_fills(address)
#print(user_fills)

# 查交易对
token1 = 'HYPE'
token2 = 'USDC'
spot_meta = info.spot_meta()
token1_index = [token['index'] for token in spot_meta['tokens'] if token['name'] == token1][0]
token2_index = [token['index'] for token in spot_meta['tokens'] if token['name'] == token2][0]
token_pair = [token1_index, token2_index]
pair_name = [pair['name'] for pair in spot_meta['universe'] if pair['tokens'] == token_pair][0]
#print(pair_name)

# 下单
#order_result = exchange.order(name=pair_name, is_buy=True, sz=0.2, limit_px=55.5, order_type={"limit": {"tif": "Gtc"}})
#print(order_result)
#order_result = exchange.order(name=pair_name, is_buy=False, sz=0.2, limit_px=77.7, order_type={"limit": {"tif": "Gtc"}})
#print(order_result)

# 查挂单
open_orders = info.open_orders(address)
#print(open_orders)

# 查订单
filled_order_status = info.query_order_by_oid(address, user_fills[0]['oid'])
#print(filled_order_status)
#open_order_status = info.query_order_by_oid(address, open_orders[0]['oid'])
#print(open_order_status)

# 撤单
#cancel_result = exchange.cancel(pair_name, open_orders[0]['oid'])
#print(cancel_result)

# 批量撤单
# cancel_list = [{"coin": pair_name, "oid": order['oid']} for order in open_orders]
# cancel_result = exchange.bulk_cancel(cancel_list)
# print(cancel_result)

# 查价格
mid_price = info.all_mids()[pair_name]
print(mid_price)
