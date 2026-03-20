import yfinance as yf
import pandas as pd

ticker = "GOOG"
start = "2025-01-01"
end = "2025-11-20"

mtr = yf.download(ticker, start=start, end=end)

# reset 索引 + 保存
mtr = mtr.reset_index()
output_name = f"{ticker.replace('.', '')}.csv"
mtr.to_csv(output_name, index=False, encoding="utf-8-sig")

print("已保存为：", output_name)


