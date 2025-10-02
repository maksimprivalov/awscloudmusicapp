import { Injectable, Inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import {environment} from '../../../environments/environment';

export type NotificationItem = {
  userId: string;
  notifId: string;
  type: string;         // npr. TRACK_ADDED
  title: string;
  body: string;
  targetType?: string;
  targetId?: string;
  contentId?: string;
  createdAt: string;    // ISO
  unread?: boolean;
  data?: string;        // JSON string (opciono)
};

@Injectable({ providedIn: 'root' })
export class NotificationsService {
  private base = environment.apiBase;
  constructor(private http: HttpClient) {}

  list(limit = 20, lastKey?: string) {
    let params = new HttpParams().set('limit', limit);
    if (lastKey) params = params.set('lastKey', lastKey);
    return this.http.get<{items: NotificationItem[]; nextKey?: string | null}>(
      `${this.base}/user/notifications`, { params }
    );
  }

  markRead(notifId: string) {
    return this.http.post<{ok: boolean}>(`${this.base}/user/notifications/read`, { notifId });
  }

  markAll() {
    return this.http.post<{ok: boolean}>(`${this.base}/user/notifications/read-all`, {});
  }
}
