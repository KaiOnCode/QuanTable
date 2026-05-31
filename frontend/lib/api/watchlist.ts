import { api } from "./client";
import type {
  Watchlist,
  WatchlistCreateRequest,
  AddTickerRequest,
  CreateAlertRequest,
  Alert,
} from "@/lib/types/models";

export const watchlistApi = {
  list(): Promise<{ watchlists: Watchlist[]; total: number }> {
    return api.get("/watchlists");
  },

  create(data: WatchlistCreateRequest): Promise<Watchlist> {
    return api.post("/watchlists", data);
  },

  get(watchlistId: string): Promise<Watchlist> {
    return api.get(`/watchlists/${watchlistId}`);
  },

  update(
    watchlistId: string,
    data: Partial<WatchlistCreateRequest>
  ): Promise<Watchlist> {
    return api.put(`/watchlists/${watchlistId}`, data);
  },

  delete(watchlistId: string): Promise<void> {
    return api.delete(`/watchlists/${watchlistId}`);
  },

  addTicker(
    watchlistId: string,
    data: AddTickerRequest
  ): Promise<void> {
    return api.post(`/watchlists/${watchlistId}/tickers`, data);
  },

  removeTicker(watchlistId: string, ticker: string): Promise<void> {
    return api.delete(`/watchlists/${watchlistId}/tickers/${ticker}`);
  },

  createAlert(
    watchlistId: string,
    data: CreateAlertRequest
  ): Promise<Alert> {
    return api.post(`/watchlists/${watchlistId}/alerts`, data);
  },
};
