import { Component } from '@angular/core';
import { Router } from '@angular/router';

type Shortcut = { icon: string; title: string; desc: string; link: string };

@Component({
  selector: 'app-home-user',
  templateUrl: './home-user.component.html',
  styleUrls: ['./home-user.component.css']
})
export class HomeUserComponent {
  shortcuts: Shortcut[] = [
    { icon: '🔍', title: 'Discover', desc: 'Search and filter content', link: '/search' },
    { icon: '⭐', title: 'Moje ocene', desc: 'Ocenjivanje sadržaja', link: '/ratings' },
    { icon: '📂', title: 'Moje liste', desc: 'Kreiraj i organizuj liste', link: '/lists' },
    { icon: '🔔', title: 'Pretplate', desc: 'Pregledaj i uređuj pretplate', link: '/subscriptions' },
    { icon: '🎯', title: 'Preporuke', desc: 'Personalizovane preporuke za tebe', link: '/recommendations' },
    { icon: '⬇️', title: 'Preuzimanja', desc: 'Preuzmi sadržaj lokalno', link: '/downloads' }
  ];

  constructor(private router: Router) {}

  goTo(link: string) {
    this.router.navigate([link]);
  }
}
