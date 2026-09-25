// albums-table.component.ts
import {Component, OnInit} from '@angular/core';
import {MusicService, TrackDto} from '../../core/music.service';
import { forkJoin, of } from 'rxjs';
import { catchError, finalize } from 'rxjs/operators';
import { HttpErrorResponse } from '@angular/common/http';

export interface AlbumRow {
  albumId: string;
  albumName?: string;
  artistName?: string;
  primaryGenre?: string;
  trackCount: number;
  exampleName?: string;
  contentIds: string[];
}

type SortKey = 'name' | 'trackNo' | 'contentId';

@Component({
  selector: 'app-albums-table',
  templateUrl: './albums-table.component.html',
  standalone: false
})
export class AlbumsTableComponent implements OnInit {

  allGenres: string[] = ['pop','rock','lofi','rap','jazz','electronic','metal','folk'];
  editGenres: string[] = [];  // multi-select bound

  albums: AlbumRow[] = [];
  loading = false;
  deleting = new Set<string>();
  error: string | null = null;

  // ====== EDIT MODAL STATE ======
  editingAlbum: AlbumRow | null = null;
  tracksForEdit: TrackDto[] = [];
  sortBy: SortKey = 'trackNo';
  modalLoading = false;
  modalError: string | null = null;

  // polja koja menjaš na albumu
  editName = '';
  editDescription = '';
  editArtistsCsv = '';             // "a1,a2,..."

  // dodavanje/uklanjanje pesama
  addContentIdsText = '';          // "cid1,cid2"
  selectedToRemove = new Set<string>();
  modalResequence = false;

  constructor(private music: MusicService) {}

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading = true; this.error = null;

    this.music.getAllTracks().subscribe({
      next: tracks => {
        // grupiši po albumId
        const by = new Map<string, TrackDto[]>();
        for (const t of tracks) {
          const id = (t.albumId ?? '').trim();
          if (!id) continue;
          if (!by.has(id)) by.set(id, []);
          by.get(id)!.push(t);
        }

        this.albums = Array.from(by.entries()).map(([albumId, arr]) => ({
          albumId,
          trackCount: arr.length,
          exampleName: arr[0]?.name,
          contentIds: arr.map(x => x.contentId)
        })).sort((a,b)=>a.albumId.localeCompare(b.albumId));

        // posle što izračunaš this.albums iz pesama...
        const ids = this.albums.map(a => a.albumId);

        forkJoin(ids.map(id => this.music.getAlbumMeta(id).pipe(catchError(() => of(null)))))
          .subscribe(async metas => {
            const byId = new Map<string, any>();
            metas.filter(Boolean).forEach((m: any) => byId.set(m.albumId, m));

            // 2) izvuci prvog autora po albumu
            const firstArtistIds = Array.from(new Set(
              metas
                .filter(m => m && Array.isArray(m.artists) && m.artists.length)
                .map((m: any) => m.artists[0])
            ));

            // 3) povuci imena autora
            const artistMap = new Map<string, string>();
            if (firstArtistIds.length) {
              const artists = await forkJoin(
                firstArtistIds.map(aid => this.music.getArtist(aid).pipe(catchError(() => of(null))))
              ).toPromise();

              artists?.forEach((a: any) => {
                if (a?.artistId) artistMap.set(a.artistId, a.name || a.artistId);
              });
            }

            // 4) upiši u tabelu
            this.albums = this.albums.map(a => {
              const meta = byId.get(a.albumId) || {};
              const firstArtistId = (meta.artists && meta.artists[0]) || null;

              // preferiraj serverom već rezolvirano ime (artistNames[0])
              const artistName =
                (Array.isArray(meta.artistNames) && meta.artistNames.length ? meta.artistNames[0] : null) ||
                (firstArtistId ? firstArtistId : '—');

              return {
                ...a,
                albumName: meta.name || a.exampleName || a.albumId,
                primaryGenre: meta.primaryGenre || undefined,
                artistName
              };
            });


            this.loading = false;
          }, (err) => {
            this.loading = false;
            this.error = err?.error?.error || err?.message || 'Failed to load';
          });
      },
      error: (err: HttpErrorResponse) => {
        this.loading = false;
        this.error = (err.error && (err.error.error || err.error.message)) || err.message || 'Failed to load';
      }
    });
  }

  openEdit(album: AlbumRow): void {
    this.editingAlbum = album;
    this.sortBy = 'trackNo';
    this.modalError = null;
    this.modalLoading = true;

    // reset formskih polja
    this.editName = '';
    this.editDescription = '';
    this.editArtistsCsv = '';
    this.addContentIdsText = '';
    this.selectedToRemove.clear();
    this.modalResequence = false;
    this.editGenres = [];

    // 1) učitaj album meta za formu
    this.music.getAlbumMeta(album.albumId).pipe(
      catchError((err: any) => {
        this.modalError = (err?.error?.error || err?.message || 'Failed to load album meta');
        return of(null);
      })
    ).subscribe(meta => {
      if (meta) {
        this.editName = meta.name || '';
        this.editDescription = meta.description || '';
        const metaGenres = Array.isArray(meta.genres) ? meta.genres : (meta.primaryGenre ? [meta.primaryGenre] : []);
        this.editGenres = metaGenres.filter(Boolean);
        this.editArtistsCsv = Array.isArray(meta.artists) ? meta.artists.join(',') : '';
      }
    });

    // 2) učitaj pesme za prikaz u modalu
    this.music.getTracksByAlbum(album.albumId)
      .pipe(finalize(() => this.modalLoading = false))
      .subscribe({
        next: list => this.tracksForEdit = this.sortTracks(list, this.sortBy),
        error: (err: HttpErrorResponse) => {
          this.modalError = (err.error && (err.error.error || err.error.message)) || err.message;
          this.tracksForEdit = [];
        }
      });
  }

  closeEdit(): void {
    this.editingAlbum = null;
    this.tracksForEdit = [];
  }

  onSortChange(key: SortKey): void {
    this.sortBy = key;
    this.tracksForEdit = this.sortTracks(this.tracksForEdit.slice(), key);
  }

  private sortTracks(list: TrackDto[], key: SortKey): TrackDto[] {
    return list.sort((a, b) => {
      const av = (a as any)[key] ?? '';
      const bv = (b as any)[key] ?? '';
      if (key === 'trackNo') return (av || 0) - (bv || 0);
      return String(av).localeCompare(String(bv));
    });
  }

  toggleRemove(t: TrackDto): void {
    if (this.selectedToRemove.has(t.contentId)) this.selectedToRemove.delete(t.contentId);
    else this.selectedToRemove.add(t.contentId);
  }

  saveEdit(): void {
    if (!this.editingAlbum) return;
    const albumId = this.editingAlbum.albumId;

    // artists
    const artistsArr = this.editArtistsCsv.split(',').map(s => s.trim()).filter(Boolean);
    // tracks to add/remove
    const addIds = this.addContentIdsText.split(',').map(s => s.trim()).filter(Boolean);
    const remIds = Array.from(this.selectedToRemove);

    // genres => prvi = primaryGenre
    const pickedGenres = (this.editGenres || []).map(g => String(g).trim()).filter(Boolean);

    const payload: any = { albumId };
    if (this.editName) payload.name = this.editName;
    if (this.editDescription !== '') payload.description = this.editDescription;
    if (artistsArr.length) payload.artists = artistsArr;
    if (addIds.length) payload.addContentIds = addIds;
    if (remIds.length) payload.removeContentIds = remIds;
    if (this.modalResequence) payload.resequence = true;

    if (pickedGenres.length) {
      payload.primaryGenre = pickedGenres[0];
      payload.genres = pickedGenres;
    }

    this.modalError = null;
    this.modalLoading = true;

    this.music.updateAlbum(payload)
      .pipe(finalize(() => this.modalLoading = false))
      .subscribe({
        next: _ => {
          alert('Album updated.');
          this.closeEdit();
          this.refresh();
        },
        error: (err: HttpErrorResponse) => {
          this.modalError = (err.error && (err.error.error || err.error.message)) || err.message || 'Update failed';
        }
      });
  }

  onDelete(album: AlbumRow): void {
    if (!confirm(`Delete album "${album.albumId}" and ALL its tracks?`)) return;
    this.error = null;
    this.deleting.add(album.albumId);
    this.music.deleteAlbum(album.albumId)
      .subscribe({
        next: res => {
          this.deleting.delete(album.albumId);
          alert(`Deleted: ${res.tracksDeleted}${res.albumDeleted ? ' + album meta' : ''}`);
          this.refresh();
        },
        error: (err: HttpErrorResponse) => {
          this.deleting.delete(album.albumId);
          this.error = (err.error && (err.error.error || err.error.message)) || err.message;
        }
      });
  }

  trackByAlbumId(_i: number, row: AlbumRow): string { return row.albumId; }
}
