#!/usr/bin/env python3
# Skeleton order manager
import logging

log = logging.getLogger("order-skeleton")

def place_order(symbol, side, quantity, price=None):
    log.info("[SKELETON] Would place order: %s %s %s @ %s", symbol, side, quantity, price)
    return {"order_id": "skeleton-1", "status": "queued"}


def cancel_order(order_id):
    log.info("[SKELETON] Would cancel order: %s", order_id)
    return {"order_id": order_id, "status": "cancelled"}
