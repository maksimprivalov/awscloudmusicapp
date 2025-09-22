import { Injectable } from '@angular/core';
import {HttpClient, HttpParams} from '@angular/common/http';
import {environment} from '../../environments/environment';


@Injectable({ providedIn: 'root' })
export class DiscoverService {
  constructor(private http: HttpClient) {}
  search(params: { genre?: string; artist?: string; album?: string; page?: number; size?: number }) {
    const qp = new HttpParams({ fromObject: {
        genre: params.genre ?? '', artist: params.artist ?? '',
        album: params.album ?? '', page: (params.page ?? 0).toString(),
        size: (params.size ?? 12).toString()
      }});
    return this.http.get<{ items: any[]; total: number }>(`${environment.apiBase}/discover`, { params: qp });
  }
}
