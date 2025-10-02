import {Component, HostListener, OnDestroy, OnInit} from '@angular/core';
import { Subscription, interval } from 'rxjs';
import {NotificationItem, NotificationsService} from './notifications.service';

@Component({
  selector: 'app-notifications-bell',
  templateUrl: './notifications-bell.component.html',
  standalone: false
})
export class NotificationsBellComponent implements OnInit, OnDestroy {
  open = false;

  items: NotificationItem[] = [];
  nextKey: string | null = null;
  loading = false;
  loadingMore = false;
  error = '';

  unreadCount = 0;

  private pollSub?: Subscription;

  constructor(private api: NotificationsService) {}

  ngOnInit(): void {
    this.refreshBadge();
    // lagani polling za badge na 30s (može i websockets kasnije)
    this.pollSub = interval(30000).subscribe(() => this.refreshBadge(false));
  }

  ngOnDestroy(): void {
    this.pollSub?.unsubscribe();
  }

  toggle(): void {
    this.open = !this.open;
    if (this.open && this.items.length === 0) {
      this.load(true);
    }
  }

  load(reset = false): void {
    if (this.loading || this.loadingMore) return;
    this.error = '';
    if (reset) {
      this.loading = true;
      this.items = [];
      this.nextKey = null;
    } else {
      if (!this.nextKey) return;
      this.loadingMore = true;
    }

    this.api.list(20, reset ? undefined : this.nextKey || undefined).subscribe({
      next: (res) => {
        if (reset) {
          this.items = res.items || [];
          this.loading = false;
        } else {
          this.items.push(...(res.items || []));
          this.loadingMore = false;
        }
        this.nextKey = res.nextKey || null;
        this.computeUnread();
      },
      error: () => {
        this.error = 'Greška pri učitavanju notifikacija.';
        this.loading = this.loadingMore = false;
      }
    });
  }

  loadMore(): void {
    this.load(false);
  }

  markRead(item: NotificationItem): void {
    if (!item.unread) return;
    this.api.markRead(item.notifId).subscribe({
      next: () => {
        item.unread = false;
        this.computeUnread();
      }
    });
  }

  markAll(): void {
    this.api.markAll().subscribe({
      next: () => {
        this.items.forEach(i => i.unread = false);
        this.unreadCount = 0;
      }
    });
  }

  private refreshBadge(fetchListIfOpen = true): void {
    // mini optimizacija: samo učitaj prvih ~10 i prebroj unread
    this.api.list(10).subscribe({
      next: (res) => {
        const list = res.items || [];
        this.unreadCount = list.filter(i => i.unread).length;
        if (this.open && fetchListIfOpen) {
          // ako je panel otvoren, osveži kompletnu listu
          this.load(true);
        }
      }
    });
  }

  private computeUnread(): void {
    this.unreadCount = this.items.filter(i => i.unread).length;
  }

  @HostListener('document:click', ['$event'])
  onDocClick(ev: MouseEvent) {
    const target = ev.target as HTMLElement;
    // zatvori ako klikneš van panela/zvonceta
    if (!target.closest('.notif-bell-wrap')) {
      this.open = false;
    }
  }
}
