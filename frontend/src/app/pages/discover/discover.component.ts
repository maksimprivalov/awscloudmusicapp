import { Component } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import {DiscoverItem, DiscoverService} from './discover.service';

@Component({
  selector: 'app-discover',
  templateUrl: './discover.component.html',
  standalone: false

})
export class DiscoverComponent {
  form: FormGroup;
  items: DiscoverItem[] = [];
  nextKey: string | null = null;
  loading = false;
  error = '';

  constructor(private fb: FormBuilder, private api: DiscoverService) {
    this.form = this.fb.group({
      genre: [''],               // '' = svi žanrovi
      type: [''],                // '' | 'album' | 'artist'
      limit: [12]
      // NOTE: artist/album polja za sada backend ne koristi; možeš ih dodati u formu kada backend omogući pretragu po imenu
    });
  }

  // reset=true -> nova pretraga, reset=false -> loadMore
  search(reset = true): void {
    this.error = '';
    if (reset) {
      this.items = [];
      this.nextKey = null;
    }
    const genreRaw = (this.form.value.genre ?? '').toString().trim();
    // backend očekuje lowercase žanr; prazno = all (mi ćemo poslati 'pop' ili sl. kada je setovano)
    const genre = genreRaw.toLowerCase();

    const type = this.form.value.type as ''|'album'|'artist';
    const limit = Number(this.form.value.limit) || 12;

    // Ako je genre prazan, smisleno je ne slati upit (backend ga traži kao obavezan).
    if (!genre) {
      this.error = 'Izaberi žanr';
      return;
    }

    this.loading = true;
    this.api.discover(genre, type || undefined, limit, this.nextKey || undefined)
      .subscribe({
        next: (res) => {
          if (reset) this.items = res.items ?? [];
          else this.items.push(...(res.items ?? []));
          this.nextKey = res.nextKey ?? null;
          this.loading = false;
        },
        error: (err) => {
          console.error(err);
          this.error = 'Greška pri učitavanju.';
          this.loading = false;
        }
      });
  }

  loadMore(): void {
    if (!this.nextKey || this.loading) return;
    this.search(false);
  }

  openDetails(it: DiscoverItem): void {
    // Za sada samo za ALBUM ima smisla (ako dodaš /content endpoint)
    console.log('Details clicked for', it);
  }
}
