import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HomeMainComponent } from './home-main/home-main.component';
import {RouterLink} from '@angular/router';



@NgModule({
  declarations: [
    HomeMainComponent

  ],
  imports: [
    CommonModule,
    RouterLink
  ]
})
export class HomePageModule { }
