import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import {environment} from '../../../environments/environment';
import {Observable} from 'rxjs';


// --- Discriminated union za grid stavke ---
export type DiscoverAlbumItem = {
  entityType: 'ALBUM';
  id: string;           // fallback id
  albumId?: string;     // mogu doći i kao albumId
  name: string;
  primaryGenre?: string;
  PK?: string;          // ponekad stigne: "ALBUM#<id>"
};

export type DiscoverArtistItem = {
  entityType: 'ARTIST';
  id: string;
  artistId?: string;
  name: string;
  primaryGenre?: string;
  PK?: string;          // ponekad stigne: "ARTIST#<id>"
};

export type DiscoverItem = DiscoverAlbumItem | DiscoverArtistItem;

export type DiscoverResponse = {
  items: DiscoverItem[];
  nextKey?: string | null;
};

// --- Detalji ---
export type Track = { contentId?: string; name?: string; trackNo?: number; durationSeconds?: number; albumId?: string };
export type Album = { albumId: string; name: string; description?: string | null; primaryGenre?: string | null };
export type Artist = { artistId: string; name: string; primaryGenre?: string | null; genres?: string[]; bio?: string | null };

export type AlbumDetails  = { album: Album;  tracks: Track[]; coverUrl?: string };
export type ArtistDetails = { artist: Artist; tracks: Track[] };

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

  getAlbumDetails(id: string): Observable<AlbumDetails> {
    return this.http.get<AlbumDetails>(`${this.base}/albumDetails/${id}`);
  }

  getArtistDetails(id: string): Observable<ArtistDetails> {
    return this.http.get<ArtistDetails>(`${this.base}/artists/${id}`);
  }


  seed(artists: number, albums: number, songsPerAlbum: number) {
    return this.http.post(`${this.base}/admin/seed`, {
      artists, albums, songs_per_album: songsPerAlbum
    });
  }

  resetMusic() {
    return this.http.post(`${this.base}/admin/reset-music`, {});
  }

  // Opcionalno, ako želiš pretplatu sa ovog ekrana:
  subscribeAlbum(albumId: string) {
    return this.http.post(`${this.base}/subscriptions`, { targetType: 'ALBUM', targetId: albumId });
  }
  subscribeArtist(artistId: string) {
    return this.http.post(`${this.base}/subscriptions`, { targetType: 'ARTIST', targetId: artistId });
  }
}
