import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import {environment} from '../../../environments/environment';

const API_BASE = 'https://j6ho5b605a.execute-api.eu-central-1.amazonaws.com/dev';

export type EntityType = 'ALBUM'|'ARTIST'|'SONG';
export interface DiscoverItem {
  id: string;
  name: string;
  entityType: EntityType;
  primaryGenre: string;
}
export interface DiscoverResponse {
  items: DiscoverItem[];
  nextKey?: string | null;
}

@Injectable({ providedIn: 'root' })
export class DiscoverService {

  private base = environment.apiBase;
  constructor(private http: HttpClient) { }

  discover(genre: string, type?: 'album'|'artist', limit = 12, lastKey?: string) {
    let params = new HttpParams().set('genre', genre).set('limit', limit);
    if (type) params = params.set('type', type);
    if (lastKey) params = params.set('lastKey', lastKey);
    return this.http.get<DiscoverResponse>(`${this.base}/discover`, { params });
  }

  seed(artists: number, albums: number, songsPerAlbum: number) {
    return this.http.post(`${this.base}/admin/seed`, {
      artists, albums, songs_per_album: songsPerAlbum
    });
  }

  resetMusic() {
    return this.http.post(`${this.base}/admin/reset-music`, {});
  }
}
