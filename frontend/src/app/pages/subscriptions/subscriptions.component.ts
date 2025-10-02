import { Component, OnInit } from '@angular/core';
import { ContentService } from '../../core/content-service';

@Component({
  selector: 'app-subscriptions',
  templateUrl: './subscriptions.component.html',
  styleUrls: ['./subscriptions.component.css'],
  standalone: false
})
export class SubscriptionsComponent implements OnInit {
  subs: any[] = [];
  loading = false;

  constructor(private api: ContentService) {}

  ngOnInit(): void {
    this.load();
  }

  load() {
    this.loading = true;
    this.api.listSubscriptions().subscribe({
      next: (res) => { 
        this.subs = res; 
        this.loading = false; 
      },
      error: () => { this.loading = false; }
    });
  }

  unsubscribe(sub: any) {
    const [targetType, targetId] = sub.targetKey.split('#');
    this.api.unsubscribeFromContent(targetType, targetId).subscribe({
      next: _ => {
        this.subs = this.subs.filter(s => s.targetKey !== sub.targetKey);
      }
    });
  }
}
