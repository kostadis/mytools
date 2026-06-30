// vue-virtual-scroller ships without first-class Vue 3 type declarations.
// Minimal shim so vue-tsc is happy; runtime is unaffected.
declare module 'vue-virtual-scroller' {
  import type { DefineComponent } from 'vue'
  export const RecycleScroller: DefineComponent<any, any, any>
  export const DynamicScroller: DefineComponent<any, any, any>
  export const DynamicScrollerItem: DefineComponent<any, any, any>
}
declare module 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
