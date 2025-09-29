import { NgModule, provideBrowserGlobalErrorListeners } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { HttpClientModule, HTTP_INTERCEPTORS } from '@angular/common/http';
import { FormsModule, ReactiveFormsModule} from '@angular/forms';

import { AppRoutingModule } from './app-routing-module';
import { App } from './app';
import { LoginComponent } from './pages/login/login.component';
import { RegisterComponent } from './pages/register/register.component';
import { DiscoverComponent } from './pages/discover/discover.component';
import { AuthInterceptor } from './core/auth-interceptor';
import { AdminUploadComponent } from './pages/admin-upload/admin-upload.component';
import { ContentListComponent } from './pages/content-list/content-list.component';
import { ContentDetailComponent } from './pages/content-detail/content-detail.component';
import { CreateArtistComponent } from './pages/create-artist/create-artist.component';
import {AlbumsTableComponent} from './pages/albums-table/albums-table.component';
import {ArtistTableComponent} from './pages/artist-table/artist-table.component';

@NgModule({
  declarations: [
    App,
    LoginComponent,
    RegisterComponent,
    DiscoverComponent,
    AdminUploadComponent,
    AdminUploadComponent,
    ContentListComponent,
    ContentDetailComponent,
    CreateArtistComponent,
    AlbumsTableComponent,
    ArtistTableComponent,
  ],
  imports: [
    BrowserModule,
    HttpClientModule,
    FormsModule,
    ReactiveFormsModule,
    AppRoutingModule,

  ],
  providers: [
    { provide: HTTP_INTERCEPTORS, useClass: AuthInterceptor, multi: true },
    provideBrowserGlobalErrorListeners()
  ],
  bootstrap: [App]
})
export class AppModule {}
