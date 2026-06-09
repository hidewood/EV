from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.bill_service import BillService
from ..utils.errors import success, error

bp = Blueprint("bill", __name__)


@bp.route("/list", methods=["GET"])
@jwt_required()
def bill_list():
    car_id = get_jwt_identity()
    date_str = request.args.get("date")
    result = BillService.query_bills(car_id, date_str)
    return success(result)


@bp.route("/detail/<int:bill_id>", methods=["GET"])
@jwt_required()
def detail(bill_id):
    car_id = get_jwt_identity()
    result = BillService.query_detail(bill_id, car_id)
    if not result:
        return error(6001)
    return success(result)


@bp.route("/pay/<int:bill_id>", methods=["POST"])
@jwt_required()
def pay(bill_id):
    car_id = get_jwt_identity()
    result, err = BillService.pay_bill(bill_id, car_id)
    if err == "bill_not_found":
        return error(6001)
    if err == "already_paid":
        return error(1001, "账单已支付")
    return success(result)
