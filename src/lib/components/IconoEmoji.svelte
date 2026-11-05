<script>
	import {
		Save, X, Download, Plus, Settings, LogOut, Search, AlertCircle,
		Trash2, RefreshCw, Send, Upload, Eye, Key, Phone, Mail, Bell,
		BellOff, Lock, Unlock, User, Users, Home, FileText, FilePen,
		ClipboardList, Package, Building2, Factory, Wrench, Hammer, Ruler,
		Scissors, Paperclip, Pin, MapPin, Map, Compass, GraduationCap, Book,
		Film, TreePine, Waves, Mountain, Trees, Sun, Snowflake, DollarSign,
		CreditCard, Receipt, Truck, Target, Star, Heart, Flame, Lightbulb,
		Megaphone, Printer, FolderOpen, Files, TrendingUp, TrendingDown,
		ArrowUp, ArrowDown, ArrowLeft, ArrowRight, Undo, Redo, EyeOff, Ban,
		Recycle, Clock, Calendar, Timer, Bot, ChartBar, Contact, Fuel, Route,
		Trophy, Car, Ticket, Folder, BookOpen, CheckCircle, XCircle,
		AlertTriangle, HelpCircle, Info, Check, Minus, Camera, Image as ImageIcon,
		Sparkles, Zap, Shield, ShieldCheck, KeyRound, Fingerprint, Smartphone,
		Monitor, Globe, Wifi, WifiOff, Cloud, CloudOff, Database, Server,
		HardDrive, Cpu, Thermometer, Droplets, Wind, Moon, CloudRain, CloudSnow,
		CloudLightning, CloudFog, Rainbow, Umbrella, Flower2, Leaf, Tent,
		Campfire, Fish, Bird, Bug, Cat, Dog, Rabbit, Turtle, Butterfly, Bee,
		Crown, Medal, Award, Gift, PartyPopper, Cake, Pizza, Coffee, Beer,
		Wine, Cocktail, CupSoda, Utensils, ChefHat, CookingPot, Microwave,
		Refrigerator, Broom, Mop, Bucket, Soap, Toilet, Bathtub, Shower,
		Construction, Hospital, School, Hotel, ShoppingBag, Landmark, Church,
		GraduationCap as GradCap, Library, Theater, Stadium, Park, Beach,
		Forest, Desert, Ocean, Lake, River, Island, Volcano, Glacier,
		Waterfall, Cave, Valley, Plateau, Mesa, Butte, Peak, Summit, Ridge,
		Range, Chain, Hospital as HospitalIcon
	} from 'lucide-svelte';

	let { emoji = '', size = 16, color = 'currentColor' } = $props();

	const mapa = {
		'💾': Save, '❌': X, '📥': Download, '➕': Plus, '⚙️': Settings,
		'🚪': LogOut, '🔍': Search, '⚠️': AlertTriangle, '⚠': AlertTriangle,
		'🗑️': Trash2, '🗑': Trash2, '🔄': RefreshCw, '📤': Send, '👁️': Eye,
		'👁': Eye, '🔑': Key, '📞': Phone, '📧': Mail, '🔔': Bell,
		'🔕': BellOff, '🔒': Lock, '🔓': Unlock, '👤': User, '👥': Users,
		'🏠': Home, '📄': FileText, '📝': FilePen, '📋': ClipboardList,
		'📦': Package, '🏢': Building2, '🏭': Factory, '🛠️': Wrench,
		'🛠': Wrench, '🔨': Hammer, '📐': Ruler, '📏': Ruler, '✂️': Scissors,
		'📎': Paperclip, '📌': Pin, '📍': MapPin, '🗺️': Map, '🧭': Compass,
		'🎓': GraduationCap, '📚': Book, '🎬': Film, '🌲': TreePine,
		'🌊': Waves, '⛰️': Mountain, '⛰': Mountain, '🌳': Trees, '☀️': Sun,
		'☀': Sun, '❄️': Snowflake, '❄': Snowflake, '💰': DollarSign,
		'💳': CreditCard, '🧾': Receipt, '🚚': Truck, '🎯': Target,
		'⭐': Star, '❤️': Heart, '❤': Heart, '🔥': Flame, '💡': Lightbulb,
		'📣': Megaphone, '🖨️': Printer, '🖨': Printer, '📂': FolderOpen,
		'📑': Files, '📈': TrendingUp, '📉': TrendingDown, '⬆️': ArrowUp,
		'⬆': ArrowUp, '⬇️': ArrowDown, '⬇': ArrowDown, '⬅️': ArrowLeft,
		'⬅': ArrowLeft, '➡️': ArrowRight, '➡': ArrowRight, '↩️': Undo,
		'↪️': Redo, '👁️': EyeOff, '🚫': Ban, '♻️': Recycle, '♻': Recycle,
		'🕐': Clock, '📅': Calendar, '⏱️': Timer, '⏱': Timer, '🤖': Bot,
		'📊': ChartBar, '📇': Contact, '⛽': Fuel, '🛣️': Route, '🛣': Route,
		'🏆': Trophy, '🚗': Car, '🎫': Ticket, '📁': Folder, '📖': BookOpen,
		'✅': CheckCircle, '☑️': CheckCircle, '❌': XCircle, '⛔': XCircle,
		'❓': HelpCircle, 'ℹ️': Info, 'ℹ': Info, '✔️': Check, '✔': Check,
		'➖': Minus, '📸': Camera, '🖼️': ImageIcon, '🖼': ImageIcon,
		'✨': Sparkles, '⚡': Zap, '🛡️': Shield, '🛡': Shield, '🔐': KeyRound,
		'🔑': Key, '📱': Smartphone, '💻': Monitor, '🌐': Globe, '📶': Wifi,
		'📵': WifiOff, '☁️': Cloud, '☁': Cloud, '🌧️': CloudRain,
		'🌨️': CloudSnow, '⛈️': CloudLightning, '🌫️': CloudFog, '🌈': Rainbow,
		'☂️': Umbrella, '☂': Umbrella, '🌸': Flower2, '🍃': Leaf,
		'⛺': Tent, '🔥': Campfire, '🐟': Fish, '🐦': Bird, '🐛': Bug,
		'🐱': Cat, '🐶': Dog, '🐰': Rabbit, '🐢': Turtle, '🦋': Butterfly,
		'🐝': Bee, '👑': Crown, '🏅': Medal, '🥇': Medal, '🥈': Medal,
		'🥉': Medal, '🎁': Gift, '🎉': PartyPopper, '🎂': Cake, '🍕': Pizza,
		'☕': Coffee, '🍺': Beer, '🍷': Wine, '🍸': Cocktail, '🥤': CupSoda,
		'🍽️': Utensils, '🍽': Utensils, '👨‍🍳': ChefHat, '🍳': CookingPot,
		'🧽': Broom, '🧹': Mop, '🪣': Bucket, '🧼': Soap, '🚽': Toilet,
		'🛁': Bathtub, '🚿': Shower, '🚧': Construction, '🏥': Hospital,
		'🏫': School, '🏨': Hotel, '🛍️': ShoppingBag, '🛍': ShoppingBag,
		'🏦': Landmark, '⛪': Church, '📖': Book, '🎭': Theater,
		'🏟️': Stadium, '🏟': Stadium, '🌳': Trees, '🌴': Trees, '🌵': Trees,
		'🏕️': Tent, '🏕': Tent, '🔥': Flame, '🐟': Fish
	};

	const IconComponent = mapa[emoji];
</script>

{#if IconComponent}
	<svelte:component this={IconComponent} {size} color={color} />
{:else}
	<span>{emoji}</span>
{/if}