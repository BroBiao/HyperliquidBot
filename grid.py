import os
import time
import math
import asyncio
import telegram
import traceback
from dotenv import load_dotenv
from hyperliquid.utils import constants
from hyperliquid.utils.error import ClientError, ServerError
import utils


# 配置参数
initialBuyQuantity=1
buyIncrement=0.1
sellQuantity=1
priceStep = 0.5
quantityDecimals = 1
priceDecimals = 3
baseAsset = 'HYPE'
quoteAsset = 'USDC'
numOrders = 3
dryRun = True

# 初始化 Hyperliquid API 客户端
address, info, exchange = utils.setup(base_url=constants.TESTNET_API_URL, skip_ws=True)

# 获取交易对名称
spot_meta = info.spot_meta()
baseAsset_index = [token['index'] for token in spot_meta['tokens'] if token['name'] == baseAsset][0]
quoteAsset_index = [token['index'] for token in spot_meta['tokens'] if token['name'] == quoteAsset][0]
token_pair = [baseAsset_index, quoteAsset_index]
pair_name = [pair['name'] for pair in spot_meta['universe'] if pair['tokens'] == token_pair][0]

# 初始化Telegram Bot
load_dotenv()
bot_token = os.getenv('BOT_TOKEN')
chat_id = os.getenv('CHAT_ID')
bot = telegram.Bot(bot_token)
loop = asyncio.get_event_loop()

# 辅助变量
buy_orders = []
sell_orders = []
last_refer_price = 0

def send_message(message):
    '''
    发送信息到Telegram
    '''
    print(message)  # 输出到日志
    if not dryRun:
        loop.run_until_complete(bot.send_message(chat_id=chat_id, text=message))

def format_price(price):
    """价格抹零，格式化为priceStep的整数倍"""
    return float(price) // priceStep * priceStep

def get_balance():
    """获取资产余额"""
    balance = {}
    user_state = info.spot_user_state(address)
    for each in user_state['balances']:
        if each['coin'] in [baseAsset, quoteAsset]:
            balance[each['coin']] = {'total': float(each['total']), 'hold': float(each['hold'])}
    return balance

def get_last_trade():
    """获取最新成交订单信息"""
    user_fills = info.user_fills(address)
    for each in user_fills:
        if each['coin'] == pair_name:
            return each

def wait_asset_unlock(attempts=5, wait_time=1):
    """检查是否所有挂单已取消，资金解锁"""
    for attempt in range(attempts):
        balance = get_balance()
        base_hold_balance = balance[baseAsset]['hold']
        quote_hold_balance = balance[quoteAsset]['hold']
        if (math.isclose(base_hold_balance, 0.0, abs_tol=1e-9) and 
            math.isclose(quote_hold_balance, 0.0, abs_tol=1e-9)):
            return True
        else:
            if attempt < attempts - 1:
                print(f"资金尚未全部解锁，等待{wait_time}秒再检查... (尝试 {attempt + 1}/{attempts})")
                time.sleep(wait_time)
    # 仍未解锁
    print("资金未能全部解锁，退出程序。")
    return False

def place_order(side, quantity, price):
    """挂单函数"""
    try:
        if side == 'BUY':
            is_buy = True
        elif side == 'SELL':
            is_buy = False
        else:
            raise ValueError('Order side should be BUY or SELL.')
        order_result = exchange.order(
            name=pair_name,
            is_buy=is_buy,
            sz=quantity,
            limit_px=price,
            order_type={"limit": {"tif": "Gtc"}}
        )
        return order_result
    except ClientError as e:
        send_message(f"挂单失败!\nerror_code: {e.error_code}\nerror_message: {e.error_message}")
        return None
    except ServerError as e:
        send_message(f"挂单服务器错误！\n{e.message}")
        return None
    except ValueError as e:
        send_message(f"挂单失败！\n{str(e)}")

def update_orders(current_price):
    """检查并更新买卖挂单，保持每侧 numOrders 个挂单"""
    global buy_orders, sell_orders, last_refer_price

    # 获取余额
    balance = get_balance()
    base_balance = balance[baseAsset]['total']
    quote_balance = balance[quoteAsset]['total']

    # 检查是否有挂单成交
    all_open_orders = info.open_orders(address)
    open_orders = [each for each in all_open_orders if each['coin'] == pair_name]
    open_orders = [order['oid'] for order in open_orders]
    filled_orders = set(buy_orders + sell_orders) - set(open_orders)

    # 获取最后一笔成交信息作为初始数据
    last_trade = get_last_trade()
    last_trade_side = last_trade['dir'].upper()
    last_trade_qty = float(last_trade['sz'])
    last_trade_price = float(last_trade['px'])

    # 挂单没有减少，分情况处理
    if not filled_orders:
        # 卖单一侧有挂单
        if sell_orders:
            print('等待挂单成交...')
            return
        # 只有买单一侧有挂单(仓位已清空，追高接货)
        elif buy_orders:
            if current_price >= (last_refer_price + priceStep):
                # 风控
                if current_price < (last_trade_price + 10 * priceStep):
                    refer_price = (last_refer_price + priceStep)
                else:
                    print('价格偏离最近成交价太远，停止挂买单')
                    return
            else:
                print('等待挂单成交...')
                return
        # 买卖两侧均无挂单(首次启动)
        else:
            refer_price = format_price(last_trade_price)
    # 挂单减少(成交或取消)
    else:
        # 确认消失的挂单是否成交
        refer_price = last_refer_price
        filled_message = ''
        last_trade_time = 0
        for order in filled_orders:
            order_info = info.query_order_by_oid(address, order)
            # 确认成交，使用最新成交订单的数据
            if order_info['order']['status'] == 'filled':
                order_side = order_info['order']['order']['side']
                if order_side == 'A':
                    filled_trade_side = 'SELL'
                elif order_side == 'B':
                    filled_trade_side = 'BUY'
                else:
                    raise ValueError('Unexpected order side (expect A or B)')
                filled_trade_qty = round(float(order_info['order']['order']['origSz']), quantityDecimals)
                filled_trade_price = round(float(order_info['order']['order']['limitPx']), priceDecimals)
                filled_message += f"{filled_trade_side} {filled_trade_qty}{baseAsset} at {filled_trade_price}\n"
                if filled_trade_side == 'BUY':
                    refer_price -= priceStep
                else:
                    refer_price += priceStep
                # 更新最新成交订单数据
                filled_time = order_info['order']['statusTimestamp']
                if filled_time > last_trade_time:
                    last_trade_time = filled_time
                    last_trade_side = filled_trade_side
                    last_trade_qty = filled_trade_qty
                elif filled_time == last_trade_time:
                    if (filled_trade_side == last_trade_side == 'BUY') and (filled_trade_price < last_trade_price):
                        last_trade_qty = filled_trade_qty
                    elif (filled_trade_side == last_trade_side == 'SELL') and (filled_trade_price > last_trade_price):
                        last_trade_qty = filled_trade_qty
                    else:
                        pass
                else:
                    pass

    # 取消剩余挂单
    if open_orders:
        cancel_list = [{"coin": pair_name, "oid": order} for order in open_orders]
        exchange.bulk_cancel(cancel_list)

    # 资金是否全部解锁
    if not wait_asset_unlock():
        send_message("资金尚未全部解锁，无法创建新挂单")
        return

    # 发送成交信息
    if filled_orders and filled_message:
        send_message(filled_message)

    buy_orders.clear()
    sell_orders.clear()

    if last_trade_side == 'BUY':
        initial_buy_qty = last_trade_qty + buyIncrement
    else:
        initial_buy_qty = initialBuyQuantity

    # 买单：往下挂 priceStep 整数倍的价格
    for i in range(numOrders):
        buy_price = round(refer_price - (i + 1) * priceStep, priceDecimals)
        buy_qty = round(initial_buy_qty + i * buyIncrement, quantityDecimals)
        if quote_balance < buy_price * buy_qty:
            send_message(f"{quoteAsset}余额: {quote_balance}，无法在{buy_price}买入{buy_qty}{baseAsset}")
            break
        if dryRun:
            print(f'在{buy_price}买入{buy_qty}{baseAsset}挂单成功')
            continue
        order = place_order('BUY', buy_qty, buy_price)
        order_status_dict = order['response']['data']['statuses'][0]
        order_status = next(iter(order_status_dict))
        if order_status != 'error':
            print(f'在{buy_price}买入{buy_qty}{baseAsset}挂单成功')
            buy_orders.append(order_status_dict[order_status]['oid'])
            quote_balance -= (buy_price * buy_qty)
        else:
            send_message(f"挂单失败！\n{order_status_dict[order_status]}")

    # 卖单：往上挂 priceStep 整数倍的价格
    for i in range(numOrders):
        sell_price = round(refer_price + (i + 1) * priceStep, priceDecimals)
        if base_balance < sellQuantity:
            print(f"{baseAsset}余额: {base_balance}，无法在{sell_price}卖出{sellQuantity}{baseAsset}")
            break
        if dryRun:
            print(f'在{sell_price}卖出{sellQuantity}{baseAsset}挂单成功')
            continue
        order = place_order('SELL', sellQuantity, sell_price)
        order_status_dict = order['response']['data']['statuses'][0]
        order_status = next(iter(order_status_dict))
        if order_status != 'error':
            print(f'在{sell_price}卖出{sellQuantity}{baseAsset}挂单成功')
            sell_orders.append(order_status_dict[order_status]['oid'])
            base_balance -= sellQuantity
        else:
            send_message(f"挂单失败！\n{order_status_dict[order_status]}")

    # 记录参考价
    last_refer_price = round(refer_price, priceDecimals)

def main():
    """主程序：实时更新价格，执行网格交易"""
    # send_message('程序启动')
    while True:
        try:
            # 获取最新价格
            current_price = float(info.all_mids()[pair_name])
            print(f"最新价格: {current_price}")

            # 更新挂单
            update_orders(current_price)

            # 间隔 5 秒更新价格
            time.sleep(5)
        except Exception as e:
            traceback.print_exc()
            send_message(str(e))
            time.sleep(5)

if __name__ == "__main__":
    main()