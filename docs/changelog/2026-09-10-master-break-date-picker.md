# Fix Master Break From/To date picker open

## Summary

From/To date fields now call `showPicker()` on click/focus and no longer nest the input inside the label, so the native calendar opens reliably inside the overflow terminal layout.
