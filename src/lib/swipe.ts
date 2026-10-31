// swipe.ts - Svelte action for swipe gestures
export interface SwipeOptions {
	threshold?: number; // Minimum distance to trigger swipe (px)
	onSwipeLeft?: () => void;
	onSwipeRight?: () => void;
}

export function swipe(node: HTMLElement, options: SwipeOptions = {}) {
	let startX = 0;
	let startY = 0;
	let isSwiping = false;
	const threshold = options.threshold || 50;

	function handleTouchStart(e: TouchEvent) {
		startX = e.touches[0].clientX;
		startY = e.touches[0].clientY;
		isSwiping = true;
	}

	function handleTouchMove(e: TouchEvent) {
		if (!isSwiping) return;
		const deltaX = e.touches[0].clientX - startX;
		const deltaY = e.touches[0].clientY - startY;

		// Only horizontal swipes
		if (Math.abs(deltaX) > Math.abs(deltaY)) {
			e.preventDefault();
			const translateX = Math.max(-100, Math.min(100, deltaX));
			node.style.transform = `translateX(${translateX}px)`;
		}
	}

	function handleTouchEnd(e: TouchEvent) {
		if (!isSwiping) return;
		isSwiping = false;
		const deltaX = e.changedTouches[0].clientX - startX;

		node.style.transition = 'transform 0.2s ease';
		if (deltaX < -threshold && options.onSwipeLeft) {
			options.onSwipeLeft();
			node.style.transform = 'translateX(0)';
		} else if (deltaX > threshold && options.onSwipeRight) {
			options.onSwipeRight();
			node.style.transform = 'translateX(0)';
		} else {
			node.style.transform = 'translateX(0)';
		}
		setTimeout(() => {
			node.style.transition = '';
		}, 200);
	}

	node.addEventListener('touchstart', handleTouchStart, { passive: true });
	node.addEventListener('touchmove', handleTouchMove, { passive: false });
	node.addEventListener('touchend', handleTouchEnd, { passive: true });

	return {
		destroy() {
			node.removeEventListener('touchstart', handleTouchStart);
			node.removeEventListener('touchmove', handleTouchMove);
			node.removeEventListener('touchend', handleTouchEnd);
		},
		update(newOptions: SwipeOptions) {
			options = newOptions;
		}
	};
}
