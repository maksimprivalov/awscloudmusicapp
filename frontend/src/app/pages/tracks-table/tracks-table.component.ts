import { Component, OnInit } from '@angular/core';
import { finalize, catchError, of, forkJoin } from 'rxjs';
import { HttpErrorResponse } from '@angular/common/http';
import { MusicService, TrackRow, UpdateTrackPayload } from '../albums-table/music.service'; // prilagodi putanju

type SortKey = 'name' | 'contentId' | 'trackNo';

@Component({
  selector: 'app-tracks-table',
  templateUrl: './tracks-table.component.html',
  standalone: false
})
export class TracksTableComponent implements OnInit {

  // tabela
  tracks: TrackRow[] = [];
  loading = false;
  error: string | null = null;
  sortBy: SortKey = 'name';

  // mapiranje artistId -> name (za prikaz)
  artistName = new Map<string, string>();

  // modal state
  editing: TrackRow | null = null;
  modalError: string | null = null;
  modalLoading = false;

  // polja za edit
  editName = '';
  editArtistsCsv = '';
  allGenres: string[] = ['pop','rock','lofi','rap','jazz','electronic','metal','folk'];
  editGenres: string[] = [];

  constructor(private music: MusicService) {}

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading = true; this.error = null;
    this.music.getTracks()
      .pipe(finalize(() => this.loading = false))
      .subscribe({
        next: list => {
          // sortiraj
          this.tracks = this.sort(list, this.sortBy);

          // skupi sve artistId da dohvatimo imena
          const ids = Array.from(new Set(
            this.tracks.flatMap(t => (t.artists || []))
          ));
          if (ids.length) {
            forkJoin(ids.map(id => this.music.getArtist(id).pipe(catchError(()=>of(null)))))
              .subscribe(resArr => {
                resArr.forEach((a: any) => {
                  if (a?.artistId) this.artistName.set(a.artistId, a.name || a.artistId);
                });
              });
          }
        },
        error: (err: HttpErrorResponse) => {
          this.error = err.error?.error || err.error?.message || err.message || 'Failed to load';
        }
      });
  }

  sort(list: TrackRow[], key: SortKey) {
    return list.slice().sort((a,b) => {
      const av:any = (a as any)[key] ?? '';
      const bv:any = (b as any)[key] ?? '';
      if (key === 'trackNo') return (av || 0) - (bv || 0);
      return String(av).localeCompare(String(bv));
    });
  }

  // ====== EDIT ======
  openEdit(t: TrackRow): void {
    this.editing = t;
    this.modalError = null;
    this.modalLoading = false;

    this.editName = t.name || '';
    this.editArtistsCsv = (t.artists || []).join(',');
    // ako nema genres u traci, ostavi prazno
    this.editGenres = Array.isArray(t.genres) ? [...t.genres] : [];
  }

  closeEdit(): void {
    this.editing = null;
  }

  saveEdit(): void {
    if (!this.editing) return;
    const t = this.editing;

    const artists = this.editArtistsCsv.split(',').map(s => s.trim()).filter(Boolean);
    const genres = (this.editGenres || []).map(g => g.trim()).filter(Boolean);

    const payload: UpdateTrackPayload = {
      contentId: t.contentId
    };

    if (this.editName && this.editName !== t.name) payload.name = this.editName;
    // po želji: pun replace liste
    payload.artists = artists;
    payload.genres = genres;

    this.modalError = null;
    this.modalLoading = true;
    this.music.updateTrack(payload)
      .pipe(finalize(() => this.modalLoading = false))
      .subscribe({
        next: _ => {
          this.closeEdit();
          this.refresh();
        },
        error: (err: HttpErrorResponse) => {
          this.modalError = err.error?.error || err.error?.message || err.message || 'Update failed';
        }
      });
  }

  // ====== DELETE ======
  onDelete(t: TrackRow): void {
    if (!confirm(`Delete track "${t.name}"?`)) return;
    this.music.deleteTrack(t.contentId).subscribe({
      next: _ => this.refresh(),
      error: (err: HttpErrorResponse) => {
        alert(err.error?.error || err.error?.message || err.message || 'Delete failed');
      }
    });
  }

  artistDisplay(t: TrackRow): string {
    const ids = t.artists || [];
    if (!ids.length) return '—';
    return ids.map(id => this.artistName.get(id) || id).join(', ');
  }
}
