import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'element-plus/dist/index.css'
import {
  Aim,
  ArrowDown,
  ArrowRight,
  Bell,
  Briefcase,
  Check,
  Cloudy,
  Connection,
  DataAnalysis,
  DataLine,
  Document,
  DocumentCopy,
  FolderOpened,
  Grid,
  List,
  Loading,
  Lock,
  Menu,
  Odometer,
  Operation,
  Plus,
  Refresh,
  Right,
  Search,
  Setting,
  Share,
  Switch,
  Tickets,
  User,
  UserFilled,
  WarningFilled
} from '@element-plus/icons-vue'
import './styles/theme.css'

import App from './App.vue'
import router from './router'

const app = createApp(App)
const icons = {
  Aim, ArrowDown, ArrowRight, Bell, Briefcase, Check, Cloudy, Connection,
  DataAnalysis, DataLine, Document, DocumentCopy, FolderOpened, Grid, List, Loading, Lock,
  Menu, Odometer, Operation, Plus, Refresh, Right, Search, Setting, Share,
  Switch, Tickets, User, UserFilled, WarningFilled
}
for (const [key, component] of Object.entries(icons)) app.component(key, component)
app.use(createPinia())
app.use(router)
app.mount('#app')
